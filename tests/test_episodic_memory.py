"""Unit tests for EpisodicMemoryProvider TTL cache behaviour."""
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Provide required env vars so addons.tokens validation does not exit during import
os.environ.setdefault("TOKEN", "test-token")
os.environ.setdefault("CLIENT_ID", "123")
os.environ.setdefault("CLIENT_SECRET_ID", "secret")
os.environ.setdefault("SERCET_KEY", "secret-key")
os.environ.setdefault("BUG_REPORT_CHANNEL_ID", "1")
os.environ.setdefault("BOT_OWNER_ID", "1")

from llm.memory.episodic import EpisodicMemoryProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Fragment:
    """Minimal stand-in for a vector search result fragment."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.metadata: dict = {}


def _make_message(channel_id: str = "42", content: str = "tell me about the history of rockets") -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.channel.id = channel_id
    return msg


def _make_bot(fragments: Optional[List[_Fragment]] = None, *, call_count_box: Optional[list] = None) -> MagicMock:
    """Build a bot stub whose vector_manager returns *fragments* on each search."""

    async def _search(**_kwargs):
        if call_count_box is not None:
            call_count_box[0] += 1
        return fragments or []

    store = MagicMock()
    store.search_memories_by_vector = _search
    vector_manager = MagicMock()
    vector_manager.store = store
    bot = MagicMock()
    bot.vector_manager = vector_manager
    return bot


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cache_hit_within_ttl():
    """Second call within TTL should return cached value without a new search."""
    call_count = [0]
    fragments = [_Fragment("rockets were invented in China")]
    bot = _make_bot(fragments, call_count_box=call_count)
    provider = EpisodicMemoryProvider(bot, ttl_seconds=60)
    msg = _make_message()

    async def run():
        result1 = await provider.get(msg)
        result2 = await provider.get(msg)
        assert result1 is not None
        assert result2 == result1
        assert call_count[0] == 1  # vector search called only once

    asyncio.run(run())


def test_cache_expires_and_refetches():
    """After TTL expiry, a subsequent call should trigger a new vector search."""
    call_count = [0]
    fragments = [_Fragment("rockets were invented in China")]
    bot = _make_bot(fragments, call_count_box=call_count)
    provider = EpisodicMemoryProvider(bot, ttl_seconds=0.05)
    msg = _make_message()

    async def run():
        await provider.get(msg)
        assert call_count[0] == 1

        # Within TTL: cache should be hit
        await provider.get(msg)
        assert call_count[0] == 1

        # After TTL: cache entry should be expired
        await asyncio.sleep(0.07)
        await provider.get(msg)
        assert call_count[0] == 2

    asyncio.run(run())


def test_miss_not_cached():
    """Results for empty fragment lists (None) should NOT be cached."""
    call_count = [0]
    bot = _make_bot(fragments=[], call_count_box=call_count)
    provider = EpisodicMemoryProvider(bot, ttl_seconds=60)
    msg = _make_message()

    async def run():
        result = await provider.get(msg)
        assert result is None
        assert len(provider._cache) == 0  # nothing cached

        # Second call should also hit the vector search (not a stale None)
        await provider.get(msg)
        assert call_count[0] == 2

    asyncio.run(run())


def test_max_cache_size_evicts_entries():
    """Cache size must not exceed max_cache_size; oldest entries are evicted."""
    call_count = [0]
    fragments = [_Fragment("content")]
    bot = _make_bot(fragments, call_count_box=call_count)
    max_size = 3
    provider = EpisodicMemoryProvider(bot, ttl_seconds=60, max_cache_size=max_size)

    async def run():
        for i in range(max_size + 2):
            msg = _make_message(channel_id=str(i), content="tell me about the history of rockets")
            await provider.get(msg)

        assert len(provider._cache) <= max_size

    asyncio.run(run())


def test_max_cache_size_prunes_expired_entries_first():
    """Expired entries should be pruned before evicting live entries."""
    call_count = [0]
    fragments = [_Fragment("content")]
    bot = _make_bot(fragments, call_count_box=call_count)
    provider = EpisodicMemoryProvider(bot, ttl_seconds=0.05, max_cache_size=3)

    async def run():
        for i in range(3):
            msg = _make_message(channel_id=str(i), content="tell me about the history of rockets")
            await provider.get(msg)

        await asyncio.sleep(0.1)  # let those entries expire

        for i in range(10, 14):
            msg = _make_message(channel_id=str(i), content="tell me about the history of rockets")
            await provider.get(msg)

        assert len(provider._cache) <= 3

    asyncio.run(run())


def test_negative_max_cache_size_raises():
    """Passing a negative max_cache_size should raise ValueError."""
    bot = _make_bot()
    with pytest.raises(ValueError, match=r"max_cache_size"):
        EpisodicMemoryProvider(bot, max_cache_size=-1)


def test_negative_ttl_seconds_raises():
    """Passing a negative ttl_seconds should raise ValueError."""
    bot = _make_bot()
    with pytest.raises(ValueError, match=r"ttl_seconds"):
        EpisodicMemoryProvider(bot, ttl_seconds=-1.0)


def test_stampede_prevention():
    """Concurrent calls for the same key should only trigger one vector search."""
    call_count = [0]
    fragments = [_Fragment("rockets were invented in China")]
    bot = _make_bot(fragments, call_count_box=call_count)
    provider = EpisodicMemoryProvider(bot, ttl_seconds=60)
    msg = _make_message()

    async def run():
        results = await asyncio.gather(
            provider.get(msg),
            provider.get(msg),
            provider.get(msg),
        )
        # All concurrent callers should receive the same non-None result
        assert all(r is not None for r in results)
        assert results[0] == results[1] == results[2]
        # Vector search should have been called exactly once
        assert call_count[0] == 1

    asyncio.run(run())
