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

    async def _fetch_and_cache(self, missing_ids: List[str]) -> None:
        events = []
        claimed = []
        for uid in missing_ids:
            if uid not in self._pending_queries:
                ev = asyncio.Event()
                self._pending_queries[uid] = ev
                events.append(ev)
                claimed.append(uid)

        if not claimed:
            return

        try:
            fetched = await self.user_manager.get_multiple_users(claimed)
            expire_at = time.monotonic() + memory_config.procedural_cache_ttl

            for uid, ev in zip(claimed, events):
                # cache an empty UserInfo if it doesn't exist, this provides negative caching
                # and stops the get loop from attempting to fetch infinitely
                info = fetched.get(uid)
                if not info:
                    info = UserInfo()
                self._cache[uid] = (info, expire_at)

                if self._pending_queries.get(uid) is ev:
                    self._pending_queries.pop(uid, None)
                ev.set()

            if len(self._cache) > self.max_cache_size:
                now_insert = time.monotonic()
                self._cache = {k: v for k, v in self._cache.items() if v[1] > now_insert}
                while len(self._cache) > self.max_cache_size:
                    oldest_key = next(iter(self._cache))
                    self._cache.pop(oldest_key, None)

        except Exception as e:
            expire_at = time.monotonic() + memory_config.procedural_cache_ttl
            for uid, ev in zip(claimed, events):
                # cache empty on exception to prevent infinite loop
                self._cache[uid] = (UserInfo(), expire_at)
                if self._pending_queries.get(uid) is ev:
                    self._pending_queries.pop(uid, None)
                ev.set()
            await func.report_error(e, "ProceduralMemoryProvider._fetch_and_cache failed")

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

        unique_ids = list(set(str(uid) for uid in user_ids))
        result: Dict[str, UserInfo] = {}

        while True:
            # 1. Deduplicate and wait for all pending events concurrently before checking cache
            pending_events = [self._pending_queries[uid] for uid in unique_ids if uid in self._pending_queries]

            if pending_events:
                # Avoid latency regressions by concurrently fetching missing keys
                now = time.monotonic()
                missing_candidates = [
                    uid for uid in unique_ids
                    if uid not in self._pending_queries and uid not in result and (uid not in self._cache or self._cache[uid][1] <= now)
                ]
                if missing_candidates:
                    asyncio.create_task(self._fetch_and_cache(missing_candidates))

                # Separate checking for pending events from claiming missing keys in main loop
                await asyncio.gather(*(e.wait() for e in pending_events))
                continue

            # 2. Synchronously check the cache
            now = time.monotonic()
            missing_ids = []
            for uid in unique_ids:
                if uid in result:
                    continue
                entry = self._cache.get(uid)
                if entry is not None and entry[1] > now:
                    result[uid] = entry[0]
                else:
                    missing_ids.append(uid)

            if not missing_ids:
                break

            # Fetch and cache missing keys directly (will loop again to pick up results)
            await self._fetch_and_cache(missing_ids)

        return ProceduralMemory(user_info=result)

    async def invalidate(self, user_id: str) -> None:
        """Evict a single user from the cache.

        Call this after a successful /memory save to ensure the next request
        reflects the updated data without waiting for TTL expiry.

        Args:
            user_id: The user_id string to remove from cache.
        """
        user_id_str = str(user_id)
        self._cache.pop(user_id_str, None)
        event = self._pending_queries.pop(user_id_str, None)
        if event:
            event.set()
