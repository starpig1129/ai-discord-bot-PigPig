import asyncio
from datetime import datetime, timezone
import sys
import types

import pytest

async def _noop_report_error(*args, **kwargs):
    return None

# Lightweight stubs for optional external dependencies used by ContextManager
fake_discord = types.ModuleType("discord")
fake_discord.Message = object
sys.modules.setdefault("discord", fake_discord)

fake_langchain_messages = types.ModuleType("langchain_core.messages")
class _BaseMessage:
    def __init__(self, content=None, name=None):
        self.content = content
        self.name = name
class _HumanMessage(_BaseMessage):
    pass
class _AIMessage(_BaseMessage):
    pass
fake_langchain_messages.BaseMessage = _BaseMessage
fake_langchain_messages.HumanMessage = _HumanMessage
fake_langchain_messages.AIMessage = _AIMessage
fake_langchain_core = types.ModuleType("langchain_core")
fake_langchain_core.__path__ = []
sys.modules["langchain_core"] = fake_langchain_core
fake_langchain_core.messages = fake_langchain_messages
sys.modules["langchain_core.messages"] = fake_langchain_messages

class _DummyLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def debug(self, *args, **kwargs):
        return None

fake_logging = types.ModuleType("addons.logging")
fake_logging.get_logger = lambda **kwargs: _DummyLogger()

fake_settings = types.ModuleType("addons.settings")
fake_settings.base_config = {}
fake_settings.llm_config = types.SimpleNamespace(llm_call_timeout=60)
fake_settings.memory_config = types.SimpleNamespace(enabled=True, procedural_cache_ttl=300.0)

fake_addons = types.ModuleType("addons")
fake_addons.logging = fake_logging
fake_addons.settings = fake_settings
sys.modules["addons"] = fake_addons
sys.modules["addons.logging"] = fake_logging
sys.modules["addons.settings"] = fake_settings

fake_function = types.ModuleType("function")
fake_function.func = types.SimpleNamespace(report_error=_noop_report_error)
sys.modules["function"] = fake_function

fake_cogs = types.ModuleType("cogs")
fake_cogs.__path__ = []
sys.modules["cogs"] = fake_cogs
fake_cogs_memory = types.ModuleType("cogs.memory")
fake_cogs_memory.__path__ = []
sys.modules["cogs.memory"] = fake_cogs_memory

fake_cogs_memory_db = types.ModuleType("cogs.memory.db")
fake_cogs_memory_db.__path__ = []
sys.modules["cogs.memory.db"] = fake_cogs_memory_db

fake_cogs_memory_db_knowledge_storage = types.ModuleType("cogs.memory.db.knowledge_storage")
class _DummyKnowledgeStorage:
    pass
fake_cogs_memory_db_knowledge_storage.KnowledgeStorage = _DummyKnowledgeStorage
sys.modules["cogs.memory.db.knowledge_storage"] = fake_cogs_memory_db_knowledge_storage

fake_cogs_memory_users = types.ModuleType("cogs.memory.users")
fake_cogs_memory_users.__path__ = []
sys.modules["cogs.memory.users"] = fake_cogs_memory_users
fake_cogs_memory_users_manager = types.ModuleType("cogs.memory.users.manager")
class _DummySQLiteUserManager:
    async def get_multiple_users(self, user_ids):
        return {}
fake_cogs_memory_users_manager.SQLiteUserManager = _DummySQLiteUserManager
sys.modules["cogs.memory.users.manager"] = fake_cogs_memory_users_manager

import llm.context_manager as context_manager
from llm.context_manager import ContextManager
from llm.memory.schema import ProceduralMemory, UserInfo


class StubShortTermProvider:
    def __init__(self, fail_with=None, messages=None):
        self.fail_with = fail_with
        self.messages = messages or []
        self.calls = 0

    async def get(self, message):
        self.calls += 1
        if self.fail_with:
            raise self.fail_with
        return self.messages


class StubProceduralProvider:
    def __init__(self):
        self.requested_ids = None

    async def get(self, user_ids):
        self.requested_ids = list(user_ids)
        return ProceduralMemory(
            user_info={uid: UserInfo(user_background="bg") for uid in user_ids}
        )


def _make_message(user_id: str = "123"):
    return types.SimpleNamespace(
        author=types.SimpleNamespace(id=user_id),
        channel=types.SimpleNamespace(name="general", id="456"),
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        content="hello",
    )


@pytest.mark.asyncio
async def test_procedural_fetch_still_runs_when_short_term_fails(monkeypatch):
    monkeypatch.setattr(context_manager, "func", types.SimpleNamespace(report_error=_noop_report_error))
    short_term_provider = StubShortTermProvider(fail_with=RuntimeError("boom"))
    procedural_provider = StubProceduralProvider()
    manager = ContextManager(short_term_provider, procedural_provider, episodic_provider=None)

    procedural_str, short_term_msgs = await manager.get_context(_make_message())

    assert short_term_msgs == []
    assert procedural_provider.requested_ids == ["123"]
    assert "User: 123" in procedural_str


@pytest.mark.asyncio
async def test_extract_error_falls_back_to_author(monkeypatch):
    monkeypatch.setattr(context_manager, "func", types.SimpleNamespace(report_error=_noop_report_error))
    short_term_provider = StubShortTermProvider(messages=[])
    procedural_provider = StubProceduralProvider()
    manager = ContextManager(short_term_provider, procedural_provider, episodic_provider=None)

    def _raise_extract(*args, **kwargs):
        raise RuntimeError("extract failed")

    monkeypatch.setattr(manager, "_extract_user_ids_from_messages", _raise_extract)

    await manager.get_context(_make_message("456"))

    assert procedural_provider.requested_ids == ["456"]


@pytest.mark.asyncio
async def test_short_term_cancellation_propagates(monkeypatch):
    monkeypatch.setattr(context_manager, "func", types.SimpleNamespace(report_error=_noop_report_error))
    short_term_provider = StubShortTermProvider(fail_with=asyncio.CancelledError())
    procedural_provider = StubProceduralProvider()
    manager = ContextManager(short_term_provider, procedural_provider, episodic_provider=None)

    with pytest.raises(asyncio.CancelledError):
        await manager.get_context(_make_message())
