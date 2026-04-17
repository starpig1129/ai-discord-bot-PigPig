"""Automatic Episodic Memory Provider for context injection.

Performs a lightweight vector search on each incoming message and returns
the top-k relevant past memory fragments as a formatted string.
Silent failure design: any error returns None without raising.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

import discord

from addons.logging import get_logger
from addons.settings import memory_config
from function import func

_LOGGER = get_logger(server_id="Bot", source="llm.memory.episodic")

# Messages shorter than this word count (after stripping mentions) are skipped
# to avoid meaningless vector searches on greetings like "hi" or "ok".
_MIN_QUERY_TOKENS = 4

# Pattern to strip Discord mention tags from message content
_MENTION_RE = re.compile(r"<@!?\d+>")


class EpisodicMemoryProvider:
    """Retrieve semantically relevant past memory fragments for context injection.

    The result is injected into procedural_context_str so both info_agent and
    message_agent receive the episodic background without extra tool calls.

    Args:
        bot: Discord bot instance (must have vector_manager attribute).
        top_k: Maximum number of fragments to retrieve. Default 3.
        max_chars: Hard character limit for the returned string. Default 1500.
    """

    def __init__(self, bot: Any, top_k: int = 3, max_chars: int = 1500) -> None:
        self.bot = bot
        self.top_k = top_k
        self.max_chars = max_chars
        self.cache_ttl = getattr(memory_config, "episodic_cache_ttl", 300.0)
        self.max_cache_size = getattr(memory_config, "episodic_max_cache_size", 1000)
        # key: (query, channel_id), value: (formatted_string, expire_at)
        self._cache: Dict[Tuple[str, str], Tuple[Optional[str], float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, message: discord.Message) -> Optional[str]:
        """Return formatted episodic context string, or None if nothing relevant.

        Runs in parallel with ProceduralMemoryProvider via asyncio.gather in
        ContextManager, so it does not add serial latency to the pipeline.

        Args:
            message: Current Discord message (provides query text and channel scope).

        Returns:
            Formatted string with past memory fragments, or None.
        """
        vector_manager = getattr(self.bot, "vector_manager", None)
        if not vector_manager or not hasattr(vector_manager, "store"):
            return None

        # Clean query: strip mentions and whitespace
        raw = getattr(message, "content", "") or ""
        query = _MENTION_RE.sub("", raw).strip()

        # Skip trivially short messages (greetings, reactions, single words)
        if len(query.split()) < _MIN_QUERY_TOKENS:
            return None

        channel_id = str(message.channel.id)
        cache_key = (query, channel_id)
        now = time.monotonic()

        async with self._lock:
            if cache_key in self._cache:
                cached_result, expire_at = self._cache[cache_key]
                if expire_at > now:
                    return cached_result
                else:
                    del self._cache[cache_key]

        try:
            fragments = await vector_manager.store.search_memories_by_vector(
                query_text=query,
                limit=self.top_k,
                channel_id=channel_id,
            )
        except Exception as e:
            await func.report_error(e, "EpisodicMemoryProvider.get: vector search failed")
            return None

        if not fragments:
            async with self._lock:
                self._cache[cache_key] = (None, now + self.cache_ttl)
                self._prune_cache()
            return None

        lines = ["--- Relevant Past Memories ---"]
        total_chars = len(lines[0])

        for i, frag in enumerate(fragments, 1):
            ts = frag.metadata.get("start_timestamp") or frag.metadata.get("timestamp")
            jump_url = frag.metadata.get("jump_url")

            # Build source label: prefer a Discord message link over plain timestamp
            if jump_url and ts:
                try:
                    unix_ts = int(float(ts))
                    source_str = f" [[來源 <t:{unix_ts}:R>]({jump_url})]"
                except Exception:
                    source_str = f" [[來源]({jump_url})]"
            elif jump_url:
                source_str = f" [[來源]({jump_url})]"
            elif ts:
                try:
                    unix_ts = int(float(ts))
                    source_str = f" [<t:{unix_ts}:R>]"
                except Exception:
                    source_str = ""
            else:
                source_str = ""

            entry = f"[memory #{i}] {frag.content}{source_str}"

            if total_chars + len(entry) + 1 > self.max_chars:
                break
            lines.append(entry)
            total_chars += len(entry) + 1

        lines.append("--- End Past Memories ---")
        _LOGGER.debug(f"Injecting {len(lines) - 2} episodic fragments into context.")

        result_str = "\n".join(lines)

        async with self._lock:
            self._cache[cache_key] = (result_str, now + self.cache_ttl)
            self._prune_cache()

        return result_str

    def _prune_cache(self) -> None:
        """Removes the oldest entries from the cache if it exceeds the max size."""
        if len(self._cache) > self.max_cache_size:
            # Sort by expiration time, keep the newest ones
            now = time.monotonic()

            # First, filter out any already expired items
            expired_keys = [k for k, v in self._cache.items() if v[1] <= now]
            for k in expired_keys:
                del self._cache[k]

            # If still too large, remove the ones that will expire soonest
            while len(self._cache) > self.max_cache_size:
                # Find the key with the smallest expiration time
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
