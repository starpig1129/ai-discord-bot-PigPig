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

    async def get(self, user_ids: List[str]) -> ProceduralMemory:
        """Fetch procedural memory with per-user TTL cache and stampede protection.

        Cache hit: return cached UserInfo without DB call.
        Cache miss: fetch from DB and store in cache.

        Args:
            user_ids: List of user id strings to fetch info for.

        Returns:
            ProceduralMemory containing a dict mapping user_id to UserInfo.
        """
        if not user_ids or not self.user_manager:
            return ProceduralMemory(user_info={})

        # Deduplicate user IDs
        user_ids = list(set(user_ids))
        result: Dict[str, UserInfo] = {}

        now = time.monotonic()
        missing_ids: List[str] = []
        pending_events: List[asyncio.Event] = []
        pending_uids: List[str] = []

        # Pass 1: check cache and active fetches
        for uid in user_ids:
            if uid in self._pending_queries:
                pending_events.append(self._pending_queries[uid])
                pending_uids.append(uid)
                continue

            entry = self._cache.get(uid)
            if entry is not None and entry[1] > now:
                result[uid] = entry[0]
            else:
                missing_ids.append(uid)

        # Pass 2: Claim missing ids immediately so other tasks don't fetch them
        events: List[asyncio.Event] = []
        for uid in missing_ids:
            event = asyncio.Event()
            events.append(event)
            self._pending_queries[uid] = event

        # Pass 3: Fetch missing and wait for pending concurrently
        async def fetch_missing():
            if not missing_ids:
                return {}
            try:
                try:
                    fetched: Dict[str, UserInfo] = await self.user_manager.get_multiple_users(
                        [str(uid) for uid in missing_ids]
                    )
                except Exception as e:
                    await func.report_error(e, "ProceduralMemoryProvider.get failed while fetching users")
                    fetched = {}

                now_after_fetch = time.monotonic()
                expire_at = now_after_fetch + memory_config.procedural_cache_ttl

                # Only cache users that actually exist in the DB response
                # to prevent positive caching of empty records and logic changes.
                for uid in missing_ids:
                    if uid in fetched:
                        self._cache[uid] = (fetched[uid], expire_at)

                if len(self._cache) > self.max_cache_size:
                    now_insert = time.monotonic()
                    self._cache = {k: v for k, v in self._cache.items() if v[1] > now_insert}

                    while len(self._cache) > self.max_cache_size:
                        oldest_key = next(iter(self._cache))
                        self._cache.pop(oldest_key)

                return fetched
            finally:
                for uid, event in zip(missing_ids, events):
                    self._pending_queries.pop(uid, None)
                    event.set()

        async def wait_for_pending():
            if not pending_events:
                return
            await asyncio.gather(*(event.wait() for event in pending_events))

        fetch_task = asyncio.create_task(fetch_missing())
        wait_task = asyncio.create_task(wait_for_pending())

        await asyncio.gather(fetch_task, wait_task)

        fetched = fetch_task.result()
        for uid in missing_ids:
            if uid in fetched:
                result[uid] = fetched[uid]

        # For pending ids, they should now be in the cache, but let's double check
        now_after_wait = time.monotonic()
        for uid in pending_uids:
            entry = self._cache.get(uid)
            if entry is not None and entry[1] > now_after_wait:
                result[uid] = entry[0]

        return ProceduralMemory(user_info=result)

    async def invalidate(self, user_id: str) -> None:
        """Evict a single user from the cache.

        Call this after a successful /memory save to ensure the next request
        reflects the updated data without waiting for TTL expiry.

        Args:
            user_id: The user_id string to remove from cache.
        """
        uid = str(user_id)
        self._cache.pop(uid, None)
        event = self._pending_queries.pop(uid, None)
        if event:
            event.set()
