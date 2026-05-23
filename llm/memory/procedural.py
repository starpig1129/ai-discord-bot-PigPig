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

        # Deduplicate list to prevent self-deadlocking on same uid
        unique_uids = list(set(str(uid) for uid in user_ids))
        result: Dict[str, UserInfo] = {}

        while True:
            now = time.monotonic()
            missing_ids: List[str] = []
            pending_events: List[asyncio.Event] = []

            for uid in unique_uids:
                entry = self._cache.get(uid)
                if entry is not None and entry[1] > now:
                    result[uid] = entry[0]
                else:
                    event = self._pending_queries.get(uid)
                    if event:
                        pending_events.append(event)
                    else:
                        missing_ids.append(uid)

            if pending_events:
                # Wait for all currently pending queries to finish, then loop to check cache again
                await asyncio.gather(*(event.wait() for event in pending_events))
                continue

            # If no pending events, we're ready to proceed with missing_ids
            break

        if missing_ids:
            # Create events for all missing_ids to block concurrent requests
            events_created: List[str] = []
            for uid in missing_ids:
                event = asyncio.Event()
                self._pending_queries[uid] = event
                events_created.append(uid)

            try:
                try:
                    fetched: Dict[str, UserInfo] = await self.user_manager.get_multiple_users(missing_ids)
                except Exception as e:
                    await func.report_error(e, "ProceduralMemoryProvider.get failed while fetching users")
                    fetched = {}

                now_fetched = time.monotonic()
                expire_at = now_fetched + memory_config.procedural_cache_ttl

                for uid in missing_ids:
                    # Update result with fetched info (could be missing/empty)
                    info = fetched.get(uid)
                    if info is not None:
                        self._cache[uid] = (info, expire_at)
                        result[uid] = info
                    else:
                        # Optional: Could cache negative hit to prevent constant re-fetching of invalid users
                        pass

                if len(self._cache) > self.max_cache_size:
                    now_insert = time.monotonic()
                    self._cache = {k: v for k, v in self._cache.items() if v[1] > now_insert}

                    while len(self._cache) > self.max_cache_size:
                        oldest_key = next(iter(self._cache))
                        self._cache.pop(oldest_key, None)
            finally:
                for uid in events_created:
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
        uid = str(user_id)
        self._cache.pop(uid, None)

        # Unblock any pending queries that were waiting on a now-invalidated result
        event = self._pending_queries.pop(uid, None)
        if event:
            event.set()
