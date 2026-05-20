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
        # prevents cache stampedes
        self._pending_queries: Dict[str, asyncio.Event] = {}

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

        now = time.monotonic()
        result: Dict[str, UserInfo] = {}
        missing_ids: List[str] = []
        events_to_set: List[str] = []

        # Deduplicate user_ids to avoid self-deadlocking if a user is passed multiple times
        unique_user_ids = []
        for uid in user_ids:
            if uid not in unique_user_ids:
                unique_user_ids.append(uid)

        try:
            # Thundering herd protection logic
            # Process sequentially to avoid complex partial failures
            for uid in unique_user_ids:
                # Wait loop in case multiple tasks race
                while uid in self._pending_queries:
                    await self._pending_queries[uid].wait()
                    now = time.monotonic()
                    entry = self._cache.get(uid)
                    if entry is not None and entry[1] > now:
                        result[uid] = entry[0]
                        break
                    # If we exit wait but no cache entry exists, loop again
                    # (another task might have failed, or we should re-register)

                if uid in result:
                    continue

                # Direct cache hit check
                now = time.monotonic()
                entry = self._cache.get(uid)
                if entry is not None and entry[1] > now:
                    result[uid] = entry[0]
                    continue

                # If still missing, we will fetch it. Register our lock for it.
                self._pending_queries[uid] = asyncio.Event()
                events_to_set.append(uid)
                missing_ids.append(uid)

            if missing_ids:
                try:
                    fetched: Dict[str, UserInfo] = await self.user_manager.get_multiple_users(
                        [str(uid) for uid in missing_ids]
                    )
                except Exception as e:
                    await func.report_error(e, "ProceduralMemoryProvider.get failed while fetching users")
                    fetched = {}

                now = time.monotonic()
                expire_at = now + memory_config.procedural_cache_ttl

                # Update cache only with successfully fetched items
                for uid in missing_ids:
                    info = fetched.get(uid)
                    if info is not None:
                        self._cache[uid] = (info, expire_at)
                        result[uid] = info

                if len(self._cache) > self.max_cache_size:
                    now_insert = time.monotonic()
                    self._cache = {k: v for k, v in self._cache.items() if v[1] > now_insert}

                    while len(self._cache) > self.max_cache_size:
                        oldest_key = next(iter(self._cache))
                        self._cache.pop(oldest_key, None)
        finally:
            # Ensure all events we created are cleared and waiters are unblocked
            # even if CancelledError occurs inside the for loop's wait()
            for uid in events_to_set:
                event = self._pending_queries.pop(uid, None)
                if event:
                    event.set()

        return ProceduralMemory(user_info=result)

    async def invalidate(self, user_id: str) -> None:
        """Evict a single user from the cache.

        Call this after a successful /memory save to ensure the next request
        reflects the updated data without waiting for TTL expiry.

        Args:
            user_id: The user_id string to remove from cache.
        """
        self._cache.pop(str(user_id), None)

        # Unblock any pending queries that were waiting on a now-invalidated result
        event = self._pending_queries.pop(str(user_id), None)
        if event:
            event.set()
