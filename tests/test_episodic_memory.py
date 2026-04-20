import asyncio
import os
import sys
import time
from pathlib import Path
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


def _make_bot(search_results=None, search_calls_counter=None):
    """Build a minimal bot stub with a vector_manager that records calls."""
    if search_results is None:
        search_results = []

    async def fake_search(query_text, limit, channel_id):
        if search_calls_counter is not None:
            search_calls_counter["n"] += 1
        return search_results

    store = MagicMock()
    store.search_memories_by_vector = fake_search
    vector_manager = MagicMock()
    vector_manager.store = store
    bot = MagicMock()
    bot.vector_manager = vector_manager
    return bot


def _make_message(content="hello world this is a test message", channel_id="100"):
    msg = MagicMock()
    msg.content = content
    msg.channel.id = channel_id
    return msg


def test_negative_max_cache_size_raises():
    bot = _make_bot()
    with pytest.raises(ValueError, match="max_cache_size"):
        EpisodicMemoryProvider(bot, max_cache_size=-1)


def test_negative_cache_ttl_raises():
    bot = _make_bot()
    with pytest.raises(ValueError, match="cache_ttl"):
        EpisodicMemoryProvider(bot, cache_ttl=-1.0)


def test_cache_hit_avoids_vector_search():
    """A second identical query within TTL should not trigger another vector search."""
    counter = {"n": 0}
    frag = MagicMock()
    frag.content = "some memory"
    frag.metadata = {}
    bot = _make_bot(search_results=[frag], search_calls_counter=counter)
    provider = EpisodicMemoryProvider(bot, cache_ttl=60.0)

    async def run():
        msg = _make_message()
        result1 = await provider.get(msg)
        assert result1 is not None
        assert counter["n"] == 1

        result2 = await provider.get(msg)
        assert result2 == result1
        assert counter["n"] == 1  # no new search

    asyncio.run(run())


def test_ttl_expiry_re_queries():
    """After TTL expiry, a repeated query should trigger a new vector search."""
    counter = {"n": 0}
    frag = MagicMock()
    frag.content = "some memory"
    frag.metadata = {}
    bot = _make_bot(search_results=[frag], search_calls_counter=counter)
    provider = EpisodicMemoryProvider(bot, cache_ttl=0.05)

    async def run():
        msg = _make_message()
        await provider.get(msg)
        assert counter["n"] == 1

        # Within TTL: cache hit
        await provider.get(msg)
        assert counter["n"] == 1

        # After TTL expiry: cache miss, re-queries
        await asyncio.sleep(0.07)
        await provider.get(msg)
        assert counter["n"] == 2

    asyncio.run(run())


def test_max_size_eviction():
    """Cache should not exceed max_cache_size entries."""
    counter = {"n": 0}
    frag = MagicMock()
    frag.content = "memory"
    frag.metadata = {}
    bot = _make_bot(search_results=[frag], search_calls_counter=counter)
    max_size = 3
    provider = EpisodicMemoryProvider(bot, max_cache_size=max_size, cache_ttl=60.0)

    async def run():
        for i in range(max_size + 5):
            msg = _make_message(
                content=f"hello world this is message number {i}",
                channel_id="100",
            )
            await provider.get(msg)

        assert len(provider._cache) <= max_size

    asyncio.run(run())


def test_invalidate_single_entry():
    """invalidate with both channel_id and query removes the exact entry."""
    counter = {"n": 0}
    frag = MagicMock()
    frag.content = "memory"
    frag.metadata = {}
    bot = _make_bot(search_results=[frag], search_calls_counter=counter)
    provider = EpisodicMemoryProvider(bot, cache_ttl=60.0)

    async def run():
        msg = _make_message(content="hello world this is a test message", channel_id="42")
        await provider.get(msg)
        assert counter["n"] == 1

        await provider.invalidate(channel_id="42", query="hello world this is a test message")

        # Cache is gone; next call re-queries
        await provider.get(msg)
        assert counter["n"] == 2

    asyncio.run(run())


def test_invalidate_channel_clears_all_channel_entries():
    """invalidate with only channel_id removes all entries for that channel."""
    frag = MagicMock()
    frag.content = "memory"
    frag.metadata = {}
    bot = _make_bot(search_results=[frag])
    provider = EpisodicMemoryProvider(bot, cache_ttl=60.0)

    async def run():
        for suffix in ["one two three four", "five six seven eight"]:
            await provider.get(_make_message(content=suffix, channel_id="99"))

        # Also populate a different channel
        await provider.get(_make_message(content="alpha beta gamma delta", channel_id="55"))

        assert any(k[0] == "99" for k in provider._cache)
        assert any(k[0] == "55" for k in provider._cache)

        await provider.invalidate(channel_id="99")

        assert not any(k[0] == "99" for k in provider._cache)
        assert any(k[0] == "55" for k in provider._cache)

    asyncio.run(run())


def test_invalidate_all_clears_entire_cache():
    """invalidate with no arguments clears the entire cache."""
    frag = MagicMock()
    frag.content = "memory"
    frag.metadata = {}
    bot = _make_bot(search_results=[frag])
    provider = EpisodicMemoryProvider(bot, cache_ttl=60.0)

    async def run():
        for ch in ["1", "2", "3"]:
            await provider.get(_make_message(channel_id=ch))

        assert len(provider._cache) > 0

        await provider.invalidate()

        assert len(provider._cache) == 0

    asyncio.run(run())
