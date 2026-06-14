"""KnowledgeMemoryProvider: provides guild and channel level knowledge with caching.

This provider handles retrieval of shared interaction knowledge (memes, facts, etc.)
and implements a TTL cache to optimize performance during message orchestration.
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional, Tuple

from cogs.memory.db.knowledge_storage import KnowledgeStorage
from function import func
from addons.settings import memory_config

class KnowledgeMemory:
    """Represents the fetched knowledge for a specific context."""
    def __init__(self, guild_knowledge: Optional[str] = None, channel_knowledge: Optional[str] = None):
        self.guild_knowledge = guild_knowledge
        self.channel_knowledge = channel_knowledge

class KnowledgeMemoryProvider:
    """Provides guild/channel knowledge with caching."""

    def __init__(self, storage: KnowledgeStorage, max_cache_size: int = 500) -> None:
        """Initialize with storage and cache limit.
        
        Args:
            storage: The KnowledgeStorage instance.
            max_cache_size: Max entries in the cache.
        """
        self.storage = storage
        self.max_cache_size = max_cache_size
        # key: (type, target_id), value: (content, expire_at)
        self._cache: Dict[Tuple[str, str], Tuple[Optional[str], float]] = {}
        self._pending_queries: Dict[Tuple[str, str], asyncio.Event] = {}

    async def get(self, guild_id: Optional[str], channel_id: str) -> KnowledgeMemory:
        """Fetch knowledge for the current guild and channel.
        
        Args:
            guild_id: Discord guild ID.
            channel_id: Discord channel ID.
            
        Returns:
            KnowledgeMemory object containing both levels of knowledge.
        """
        # Fetch both levels concurrently to optimize orchestration latency
        tasks = []
        if guild_id:
            tasks.append(self._get_single("guild", guild_id))
        else:
            tasks.append(asyncio.sleep(0, result=None))
            
        tasks.append(self._get_single("channel", channel_id))

        results = await asyncio.gather(*tasks)
        
        return KnowledgeMemory(
            guild_knowledge=results[0],
            channel_knowledge=results[1]
        )

    async def _get_single(self, target_type: str, target_id: str) -> Optional[str]:
        """Internal helper with TTL cache and thundering herd protection."""
        cache_key = (target_type, target_id)
        
        while True:
            now = time.monotonic()

            if cache_key in self._pending_queries:
                await self._pending_queries[cache_key].wait()
                continue

            entry = self._cache.get(cache_key)
            if entry is not None and entry[1] > now:
                return entry[0]

            # Cache miss, register event and fetch
            self._pending_queries[cache_key] = asyncio.Event()
            break
            
        try:
            try:
                content = await self.storage.get_knowledge(target_type, target_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await func.report_error(e, f"KnowledgeMemoryProvider fetch failed ({target_type}:{target_id})")
                content = None

            now = time.monotonic()
            expire_at = now + getattr(memory_config, "knowledge_cache_ttl", 300) # Default 5 mins
            self._cache[cache_key] = (content, expire_at)
            
            if len(self._cache) > self.max_cache_size:
                now_insert = time.monotonic()
                self._cache = {k: v for k, v in self._cache.items() if v[1] > now_insert}
                while len(self._cache) > self.max_cache_size:
                    oldest_key = next(iter(self._cache))
                    self._cache.pop(oldest_key, None)
                    
            return content
        finally:
            event = self._pending_queries.pop(cache_key, None)
            if event:
                event.set()

    async def invalidate(self, target_type: str, target_id: str) -> None:
        """Invalidate cache for a specific target."""
        cache_key = (target_type, target_id)
        self._cache.pop(cache_key, None)
        event = self._pending_queries.pop(cache_key, None)
        if event:
            event.set()
