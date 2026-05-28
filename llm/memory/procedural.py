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

        # deduplicate
        user_ids = list(set(str(uid) for uid in user_ids))
        result: Dict[str, UserInfo] = {}

        while True:
            now = time.monotonic()
            missing_ids: List[str] = []
            pending_events: List[asyncio.Event] = []

            for uid in user_ids:
                entry = self._cache.get(uid)
                if entry is not None and entry[1] > now:
                    result[uid] = entry[0]
                elif uid in self._pending_queries:
                    pending_events.append(self._pending_queries[uid])
                else:
                    missing_ids.append(uid)

            if pending_events:
                await asyncio.gather(*(event.wait() for event in pending_events))
                # restart loop to check cache again
                continue

            # if no missing ids and no pending events, we're done
            if not missing_ids:
                break

            # Claim missing_ids
            for uid in missing_ids:
                self._pending_queries[uid] = asyncio.Event()

            try:
                try:
                    fetched: Dict[str, UserInfo] = await self.user_manager.get_multiple_users(missing_ids)
                except Exception as e:
                    await func.report_error(e, "ProceduralMemoryProvider.get failed while fetching users")
                    fetched = {}

                now_insert = time.monotonic()
                expire_at = now_insert + memory_config.procedural_cache_ttl

                for uid in missing_ids:
                    info = fetched.get(uid, UserInfo(user_background="", procedural_memory=""))
                    self._cache[uid] = (info, expire_at)
                    result[uid] = info

                if len(self._cache) > self.max_cache_size:
                    self._cache = {k: v for k, v in self._cache.items() if v[1] > now_insert}

                    while len(self._cache) > self.max_cache_size:
                        oldest_key = next(iter(self._cache))
                        self._cache.pop(oldest_key)
            finally:
                for uid in missing_ids:
                    event = self._pending_queries.pop(uid, None)
                    if event:
                        event.set()

            break

        return ProceduralMemory(user_info=result)

    async def invalidate(self, user_id: str) -> None:
        """Evict a single user from the cache.

        Call this after a successful /memory save to ensure the next request
        reflects the updated data without waiting for TTL expiry.

        Args:
            user_id: The user_id string to remove from cache.
        """
        uid_str = str(user_id)
        self._cache.pop(uid_str, None)
        event = self._pending_queries.pop(uid_str, None)
        if event:
            event.set()
