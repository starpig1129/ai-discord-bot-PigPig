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

        Args:
            user_ids: List of user id strings to fetch info for.

        Returns:
            ProceduralMemory containing a dict mapping user_id to UserInfo.
        """
        if not user_ids or not self.user_manager:
            return ProceduralMemory(user_info={})

        unique_ids = list(set(str(uid) for uid in user_ids))
        result: Dict[str, UserInfo] = {}
        attempted_ids = set()

        while True:
            now = time.monotonic()
            missing_ids: List[str] = []
            pending_events: List[asyncio.Event] = []

            # Pass 1: Check cache and pending queries synchronously
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
                elif uid not in attempted_ids:
                    missing_ids.append(uid)

            if not pending_events and not missing_ids:
                break # All IDs are resolved or attempted and failed

            # Pass 2: Claim missing IDs by creating pending events
            for uid in missing_ids:
                event = asyncio.Event()
                self._pending_queries[uid] = event

            # Prepare awaitables for fetching and waiting concurrently
            awaitables = []
            if missing_ids:
                # Add fetch task
                awaitables.append(self.user_manager.get_multiple_users(missing_ids))

            # Add waiting for pending events
            if pending_events:
                awaitables.extend(e.wait() for e in pending_events)

            fetched: Dict[str, UserInfo] = {}
            if awaitables:
                try:
                    # Execute fetch and waits concurrently
                    results = await asyncio.gather(*awaitables)
                    # If we fetched missing_ids, the result is the first item in results
                    if missing_ids:
                        fetched = results[0]
                except Exception as e:
                    if missing_ids:
                        await func.report_error(e, "ProceduralMemoryProvider.get failed while fetching users")

            # Process fetch results if any
            if missing_ids:
                try:
                    # Process results synchronously
                    expire_at = time.monotonic() + memory_config.procedural_cache_ttl
                    for uid in missing_ids:
                        attempted_ids.add(uid)
                        info = fetched.get(uid)
                        if info is not None:
                            self._cache[uid] = (info, expire_at)
                            result[uid] = info

                    # Cache eviction
                    if len(self._cache) > self.max_cache_size:
                        now_insert = time.monotonic()
                        self._cache = {k: v for k, v in self._cache.items() if v[1] > now_insert}
                        while len(self._cache) > self.max_cache_size:
                            oldest_key = next(iter(self._cache))
                            self._cache.pop(oldest_key)
                finally:
                    # Always safely pop and signal waiting tasks
                    for uid in missing_ids:
                        event = self._pending_queries.pop(uid, None)
                        if event is not None:
                            event.set()

        return ProceduralMemory(user_info=result)

    async def invalidate(self, user_id: str) -> None:
        """Evict a single user from the cache and unblock pending queries.

        Call this after a successful /memory save to ensure the next request
        reflects the updated data without waiting for TTL expiry.

        Args:
            user_id: The user_id string to remove from cache.
        """
        uid = str(user_id)
        self._cache.pop(uid, None)
        event = self._pending_queries.pop(uid, None)
        if event is not None:
            event.set()
