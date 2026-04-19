"""Automatic Episodic Memory Provider for context injection.

Performs a lightweight vector search on each incoming message and returns
the top-k relevant past memory fragments as a formatted string.
Silent failure design: any error returns None without raising.
"""
from __future__ import annotations

import re
import time
import asyncio
from typing import TYPE_CHECKING, Any, Optional, Dict, Tuple

import discord

from addons.logging import get_logger
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
        ttl_seconds: Cache time-to-live in seconds. Default 300.0.
        max_cache_size: Maximum cache size. Default 1000.
    """

    def __init__(self, bot: Any, top_k: int = 3, max_chars: int = 1500, ttl_seconds: float = 300.0, max_cache_size: int = 1000) -> None:
        self.bot = bot
        self.top_k = top_k
        self.max_chars = max_chars
        self.ttl_seconds = ttl_seconds
        self.max_cache_size = max_cache_size
        self._cache: Dict[str, Tuple[Optional[str], float]] = {}
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
        cache_key = f"{channel_id}:{query}"
        now = time.monotonic()

        async with self._lock:
            entry = self._cache.get(cache_key)
            if entry is not None and entry[1] > now:
                return entry[0]

        try:
            fragments = await vector_manager.store.search_memories_by_vector(
                query_text=query,
                limit=self.top_k,
                channel_id=channel_id,
            )
        except Exception as e:
            await func.report_error(e, "EpisodicMemoryProvider.get: vector search failed")
            return None

        result_str = None
        if fragments:

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

        expire_at = time.monotonic() + self.ttl_seconds
        async with self._lock:
            self._cache[cache_key] = (result_str, expire_at)

            if len(self._cache) > self.max_cache_size:
                now_insert = time.monotonic()
                self._cache = {k: v for k, v in self._cache.items() if v[1] > now_insert}

                while len(self._cache) > self.max_cache_size:
                    oldest_key = next(iter(self._cache))
                    self._cache.pop(oldest_key)

        return result_str
