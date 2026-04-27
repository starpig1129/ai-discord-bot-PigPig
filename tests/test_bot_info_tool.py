"""Tests for llm/tools/bot_info.py — BotInfoTools."""
import sys
import types
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

project_root = Path(__file__).resolve().parent.parent


# ── Stub modules that require production environment ──────────────────────────

class _DummyLogger:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def debug(self, *a, **kw): pass

fake_addons = types.ModuleType("addons")
fake_addons.__path__ = [str(project_root / "addons")]

fake_logging = types.ModuleType("addons.logging")
fake_logging.get_logger = lambda **kwargs: _DummyLogger()

fake_settings = types.ModuleType("addons.settings")
fake_settings.update_config = types.SimpleNamespace(github={})

fake_addons.logging = fake_logging
fake_addons.settings = fake_settings
sys.modules.setdefault("addons", fake_addons)
sys.modules.setdefault("addons.logging", fake_logging)
sys.modules.setdefault("addons.settings", fake_settings)

fake_function = types.ModuleType("function")
fake_function.func = types.SimpleNamespace(
    report_error=AsyncMock(return_value=None)
)
sys.modules.setdefault("function", fake_function)

# Stub langchain_core so StructuredTool import works without full install
try:
    from langchain_core.tools.structured import StructuredTool  # noqa: F401
except ImportError:
    fake_lc_tools = types.ModuleType("langchain_core.tools.structured")
    class _FakeStructuredTool:
        @classmethod
        def from_function(cls, func=None, name=None, metadata=None, coroutine=None, **kwargs):
            obj = cls()
            obj.func = func
            obj.coroutine = coroutine
            obj.metadata = metadata or {}
            obj.name = name or getattr(coroutine or func, "__name__", "tool")
            return obj
    fake_lc_tools.StructuredTool = _FakeStructuredTool
    sys.modules["langchain_core"] = types.ModuleType("langchain_core")
    sys.modules["langchain_core.tools"] = types.ModuleType("langchain_core.tools")
    sys.modules["langchain_core.tools.structured"] = fake_lc_tools

# Also stub VersionChecker so tests never hit the network
fake_update_checker = types.ModuleType("addons.update.checker")
class _FakeVersionChecker:
    def __init__(self, github_config):
        self.github_config = github_config
    async def check_for_updates(self):
        return {
            "current_version": "v3.1.0",
            "latest_version": "v3.2.0",
            "update_available": True,
            "release_notes": "- New feature A\n- Bug fix B",
            "published_at": "2026-04-20T10:00:00Z",
        }
fake_update_checker.VersionChecker = _FakeVersionChecker
sys.modules["addons.update"] = types.ModuleType("addons.update")
sys.modules["addons.update.checker"] = fake_update_checker

# ── Now import the module under test ─────────────────────────────────────────
import importlib
bot_info = importlib.import_module("llm.tools.bot_info")
BotInfoTools = bot_info.BotInfoTools

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_get_tools_returns_one_tool():
    """BotInfoTools.get_tools() must return exactly one tool."""
    runtime = types.SimpleNamespace(logger=_DummyLogger())
    tools = BotInfoTools(runtime).get_tools()
    assert len(tools) == 1


def test_tool_tagged_for_info_agent():
    """The tool must carry target_agent_mode == 'info' in its metadata."""
    runtime = types.SimpleNamespace(logger=_DummyLogger())
    tool = BotInfoTools(runtime).get_tools()[0]
    assert tool.metadata.get("target_agent_mode") == "info"


def test_tool_name():
    """Tool must be named 'get_bot_changelog'."""
    runtime = types.SimpleNamespace(logger=_DummyLogger())
    tool = BotInfoTools(runtime).get_tools()[0]
    assert tool.name == "get_bot_changelog"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_changelog_output_contains_versions():
    """Calling get_bot_changelog must include current and latest version."""
    runtime = types.SimpleNamespace(logger=_DummyLogger())
    tool = BotInfoTools(runtime).get_tools()[0]
    result = _run(tool.coroutine())
    assert "v3.1.0" in result
    assert "v3.2.0" in result


def test_changelog_output_contains_release_notes():
    """Calling get_bot_changelog must include release notes from GitHub."""
    runtime = types.SimpleNamespace(logger=_DummyLogger())
    tool = BotInfoTools(runtime).get_tools()[0]
    result = _run(tool.coroutine())
    assert "New feature A" in result
    assert "Bug fix B" in result


def test_changelog_output_update_available():
    """Result must indicate an update is available when update_available=True."""
    runtime = types.SimpleNamespace(logger=_DummyLogger())
    tool = BotInfoTools(runtime).get_tools()[0]
    result = _run(tool.coroutine())
    assert "update" in result.lower() or "新版本" in result


def test_changelog_error_handling():
    """When VersionChecker raises, tool returns error string instead of raising."""
    import llm.tools.bot_info as bi

    class _ErrorChecker:
        def __init__(self, _): pass
        async def check_for_updates(self):
            raise RuntimeError("network failure")

    original = bi.VersionChecker
    bi.VersionChecker = _ErrorChecker
    try:
        runtime = types.SimpleNamespace(logger=_DummyLogger())
        tool = BotInfoTools(runtime).get_tools()[0]
        result = _run(tool.coroutine())
        assert "error" in result.lower() or "錯誤" in result
    finally:
        bi.VersionChecker = original
