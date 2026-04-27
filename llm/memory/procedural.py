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

        now = time.monotonic()
        result: Dict[str, UserInfo] = {}
        missing_ids: List[str] = []

        async with self._lock:
            for uid in user_ids:
                entry = self._cache.get(uid)
                if entry is not None and entry[1] > now:
                    result[uid] = entry[0]
                else:
                    missing_ids.append(uid)

        if missing_ids:
            try:
                fetched: Dict[str, UserInfo] = await self.user_manager.get_multiple_users(
                    [str(uid) for uid in missing_ids]
                )
            except Exception as e:
                await func.report_error(e, "ProceduralMemoryProvider.get failed while fetching users")
                fetched = {}

            expire_at = time.monotonic() + memory_config.procedural_cache_ttl
            async with self._lock:
                for uid, info in fetched.items():
                    self._cache[uid] = (info, expire_at)
                    result[uid] = info

                if len(self._cache) > self.max_cache_size:
                    now_insert = time.monotonic()
                    self._cache = {k: v for k, v in self._cache.items() if v[1] > now_insert}

                    while len(self._cache) > self.max_cache_size:
                        oldest_key = next(iter(self._cache))
                        self._cache.pop(oldest_key)

        return ProceduralMemory(user_info=result)

    async def invalidate(self, user_id: str) -> None:
        """Evict a single user from the cache.

        Call this after a successful /memory save to ensure the next request
        reflects the updated data without waiting for TTL expiry.

        Args:
            user_id: The user_id string to remove from cache.
        """
        async with self._lock:
            self._cache.pop(str(user_id), None)
