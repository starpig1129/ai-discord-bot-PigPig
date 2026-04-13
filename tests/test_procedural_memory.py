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
