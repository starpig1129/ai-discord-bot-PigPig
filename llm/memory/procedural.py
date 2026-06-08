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
        """Fetch procedural memory with per-user TTL cache and thundering herd protection.

        Cache hit: return cached UserInfo without DB call.
        Cache miss: fetch from DB and store in cache.

        Args:
            user_ids: List of user id strings to fetch info for.

        Returns:
            ProceduralMemory containing a dict mapping user_id to UserInfo.
        """
        if not user_ids or not self.user_manager:
            return ProceduralMemory(user_info={})

        # Deduplicate user IDs to prevent redundant processing
        unique_ids = list(dict.fromkeys(user_ids))
        result: Dict[str, UserInfo] = {}
        attempted_ids = set()

        while True:
            now = time.monotonic()
            missing_ids: List[str] = []
            pending_events: List[asyncio.Event] = []

            for uid in unique_ids:
                if uid in result:
                    continue

                entry = self._cache.get(uid)
                if entry is not None and entry[1] > now:
                    result[uid] = entry[0]
                    continue

                event = self._pending_queries.get(uid)
                if event is not None:
                    pending_events.append(event)
                else:
                    if uid not in attempted_ids:
                        missing_ids.append(uid)

            if pending_events:
                # Wait for all pending events simultaneously before trying again
                await asyncio.gather(*(event.wait() for event in pending_events))
                continue

            if not missing_ids:
                break

            # Mark missing_ids as attempted to break potential infinite loop on permanent failure
            attempted_ids.update(missing_ids)

            # Claim the missing keys by creating events for them
            my_events = {}
            for uid in missing_ids:
                event = asyncio.Event()
                self._pending_queries[uid] = event
                my_events[uid] = event

            try:
                fetched: Dict[str, UserInfo] = {}
                try:
                    fetched = await self.user_manager.get_multiple_users(
                        [str(uid) for uid in missing_ids]
                    )
                except Exception as e:
                    await func.report_error(e, "ProceduralMemoryProvider.get failed while fetching users")

                expire_at = time.monotonic() + memory_config.procedural_cache_ttl

                # Update cache synchronously
                for uid in missing_ids:
                    # We store an empty UserInfo for missing users (negative caching)
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
                # Always clean up the events and wake up waiting tasks
                for uid, event in my_events.items():
                    self._pending_queries.pop(uid, None)
                    event.set()

            # Loop again. Any `missing_ids` we just fetched or negative-cached
            # will hit the result/cache check at the top.

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
