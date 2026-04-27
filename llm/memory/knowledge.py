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
        self._lock = asyncio.Lock()

    async def get(self, guild_id: Optional[str], channel_id: str) -> KnowledgeMemory:
        """Fetch knowledge for the current guild and channel.
        
        Args:
            guild_id: Discord guild ID.
            channel_id: Discord channel ID.
            
        Returns:
            KnowledgeMemory object containing both levels of knowledge.
        """
        guild_knowledge = None
        if guild_id:
            guild_knowledge = await self._get_single("guild", guild_id)
            
        channel_knowledge = await self._get_single("channel", channel_id)
        
        return KnowledgeMemory(
            guild_knowledge=guild_knowledge,
            channel_knowledge=channel_knowledge
        )

    async def _get_single(self, target_type: str, target_id: str) -> Optional[str]:
        """Internal helper with TTL cache."""
        now = time.monotonic()
        cache_key = (target_type, target_id)
        
        async with self._lock:
            entry = self._cache.get(cache_key)
            if entry is not None and entry[1] > now:
                return entry[0]
        
        # Cache miss
        try:
            content = await self.storage.get_knowledge(target_type, target_id)
        except Exception as e:
            await func.report_error(e, f"KnowledgeMemoryProvider fetch failed ({target_type}:{target_id})")
            content = None
            
        # Update cache
        expire_at = now + getattr(memory_config, "procedural_cache_ttl", 300) # Default 5 mins
        async with self._lock:
            self._cache[cache_key] = (content, expire_at)
            
            # Prune cache if needed
            if len(self._cache) > self.max_cache_size:
                self._cache = {k: v for k, v in self._cache.items() if v[1] > now}
                while len(self._cache) > self.max_cache_size:
                    oldest_key = next(iter(self._cache))
                    self._cache.pop(oldest_key)
                    
        return content

    async def invalidate(self, target_type: str, target_id: str) -> None:
        """Invalidate cache for a specific target."""
        async with self._lock:
            self._cache.pop((target_type, target_id), None)
