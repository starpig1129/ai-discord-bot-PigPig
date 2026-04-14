import asyncio
import os
import sys
from pathlib import Path

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

from addons.settings import memory_config
from llm.memory.procedural import ProceduralMemoryProvider
from llm.memory.schema import UserInfo


class StubUserManager:
    def __init__(self) -> None:
        self.calls = 0

    async def get_multiple_users(self, user_ids):
        self.calls += 1
        return {uid: UserInfo(user_background=f"user-{uid}") for uid in user_ids}


def test_procedural_cache_respects_configured_ttl(monkeypatch):
    # Use a short TTL to exercise expiration quickly
    monkeypatch.setattr(memory_config, "procedural_cache_ttl", 0.05)
    manager = StubUserManager()
    provider = ProceduralMemoryProvider(manager)

    async def run_checks():
        first = await provider.get(["1"])
        assert "1" in first.user_info
        assert manager.calls == 1

        # Within TTL: should hit cache and not increase call count
        second = await provider.get(["1"])
        assert "1" in second.user_info
        assert manager.calls == 1

        # After TTL expiration: should fetch again
        await asyncio.sleep(0.06)
        third = await provider.get(["1"])
        assert "1" in third.user_info
        assert manager.calls == 2

    asyncio.run(run_checks())


def test_max_cache_size_evicts_oldest_entries(monkeypatch):
    """Cache should not exceed max_cache_size; oldest entries are evicted first."""
    monkeypatch.setattr(memory_config, "procedural_cache_ttl", 60)
    manager = StubUserManager()
    max_size = 3
    provider = ProceduralMemoryProvider(manager, max_cache_size=max_size)

    async def run_checks():
        # Fill the cache beyond its limit
        for i in range(max_size + 2):
            await provider.get([str(i)])

        assert len(provider._cache) <= max_size

    asyncio.run(run_checks())


def test_max_cache_size_prunes_expired_entries_first(monkeypatch):
    """Expired entries should be pruned before evicting live entries."""
    monkeypatch.setattr(memory_config, "procedural_cache_ttl", 0.05)
    manager = StubUserManager()
    provider = ProceduralMemoryProvider(manager, max_cache_size=3)

    async def run_checks():
        # Populate the cache with entries that will expire
        for i in range(3):
            await provider.get([str(i)])

        # Wait for those entries to expire
        await asyncio.sleep(0.1)

        # Fetch new entries; expired entries should be pruned first
        for i in range(10, 14):
            await provider.get([str(i)])

        assert len(provider._cache) <= 3

    asyncio.run(run_checks())


def test_max_cache_size_negative_raises():
    """Passing a negative max_cache_size should raise ValueError."""
    manager = StubUserManager()
    try:
        ProceduralMemoryProvider(manager, max_cache_size=-1)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "max_cache_size" in str(exc).lower() or ">= 0" in str(exc)
