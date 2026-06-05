import asyncio
import time
from typing import Dict, List, Optional, Tuple

from llm.memory.schema import ProceduralMemory, UserInfo
from cogs.memory.users.manager import SQLiteUserManager
from function import func
from addons.settings import memory_config


class ProceduralMemoryProvider:
    """Provides procedural memory for multiple users with per-user TTL cache.

    The provider fetches UserInfo for each user_id using the provided user manager
    and caches results per user_id to avoid redundant DB calls within the TTL window.
    """

    def __init__(self, user_manager: SQLiteUserManager, max_cache_size: int = 1000) -> None:
        """Initializes the provider with a user manager instance and cache size limit.

        Args:
            user_manager: Manager used to fetch user information from storage.
            max_cache_size: Maximum number of user entries to retain in the cache
                before pruning. Must be a non-negative integer.

        Raises:
            ValueError: If max_cache_size is negative.
        """
        if max_cache_size < 0:
            raise ValueError("max_cache_size must be >= 0")
        self.user_manager = user_manager
        self.max_cache_size = max_cache_size
        # key: user_id (str), value: (UserInfo, expire_at: float monotonic)
        self._cache: Dict[str, Tuple[UserInfo, float]] = {}
        self._pending_queries: Dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def get(self, user_ids: List[str]) -> ProceduralMemory:
        """Fetch procedural memory with per-user TTL cache.

        Cache hit: return cached UserInfo without DB call.
        Cache miss: fetch from DB and store in cache.

        Args:
            user_ids: List of user id strings to fetch info for.

        Returns:
            ProceduralMemory containing a dict mapping user_id to UserInfo.
        """
        if not user_ids or not self.user_manager:
            return ProceduralMemory(user_info={})

        unique_uids = list(set(str(uid) for uid in user_ids))
        result: Dict[str, UserInfo] = {}
        attempted_ids = set()

        while True:
            now = time.monotonic()
            missing_ids: List[str] = []
            pending_events: List[asyncio.Event] = []

            async with self._lock:
                for uid in unique_uids:
                    if uid in result:
                        continue
                    entry = self._cache.get(uid)
                    if entry is not None and entry[1] > now:
                        result[uid] = entry[0]
                    elif uid in attempted_ids:
                        # We tried to fetch it, and it's not in cache, so it genuinely missed.
                        # Do not keep looping forever trying to fetch it.
                        continue
                    elif uid in self._pending_queries:
                        pending_events.append(self._pending_queries[uid])
                    else:
                        missing_ids.append(uid)
                        self._pending_queries[uid] = asyncio.Event()

            if not pending_events and not missing_ids:
                break

            tasks = []

            if missing_ids:
                attempted_ids.update(missing_ids)
                async def fetch_missing() -> None:
                    try:
                        fetched: Dict[str, UserInfo] = {}
                        try:
                            fetched = await self.user_manager.get_multiple_users(missing_ids)
                        except Exception as e:
                            await func.report_error(e, "ProceduralMemoryProvider.get failed while fetching users")

                        if fetched:
                            expire_at = time.monotonic() + memory_config.procedural_cache_ttl
                            async with self._lock:
                                for uid, info in fetched.items():
                                    self._cache[uid] = (info, expire_at)

                                if len(self._cache) > self.max_cache_size:
                                    now_insert = time.monotonic()
                                    self._cache = {k: v for k, v in self._cache.items() if v[1] > now_insert}

                                    while len(self._cache) > self.max_cache_size:
                                        oldest_key = next(iter(self._cache))
                                        self._cache.pop(oldest_key)
                    finally:
                        # asyncio event loop makes dict operations safe from thread pre-emption.
                        # Do not use async with self._lock here to prevent deadlocks when task is cancelled.
                        for uid in missing_ids:
                            event = self._pending_queries.pop(uid, None)
                            if event:
                                event.set()

                tasks.append(asyncio.create_task(fetch_missing()))

            if pending_events:
                # gather returns a Future, which we can wrap in a task or just await directly.
                # Since we want to await fetch_missing AND pending_events concurrently,
                # we can define a small async function or just create tasks for the awaits.
                async def wait_for_events() -> None:
                    await asyncio.gather(*(e.wait() for e in pending_events))
                tasks.append(asyncio.create_task(wait_for_events()))

            if tasks:
                await asyncio.gather(*tasks)

            # Loop again to read newly fetched or pending items into `result`
            continue

        return ProceduralMemory(user_info=result)

    async def invalidate(self, user_id: str) -> None:
        """Evict a single user from the cache.

        Call this after a successful /memory save to ensure the next request
        reflects the updated data without waiting for TTL expiry.

        Args:
            user_id: The user_id string to remove from cache.
        """
        async with self._lock:
            uid = str(user_id)
            self._cache.pop(uid, None)
            event = self._pending_queries.pop(uid, None)
            if event:
                event.set()
