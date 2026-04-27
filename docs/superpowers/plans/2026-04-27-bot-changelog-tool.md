# Bot Changelog Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `get_bot_changelog` LangChain tool in `llm/tools/bot_info.py` that wraps `VersionChecker` so the info_agent can answer questions about recent bot updates.

**Architecture:** `BotInfoTools` follows the existing `*Tools` pattern — constructor takes `runtime`, `get_tools()` returns a list of `StructuredTool`. The tool calls `VersionChecker(update_config.github).check_for_updates()` and formats the result as a human-readable string. Tagged `target_agent_mode = "info"` so `tools_factory.py` routes it to the info_agent automatically.

**Tech Stack:** Python 3.11, LangChain `StructuredTool`, `addons.update.checker.VersionChecker`, `addons.settings.update_config`

---

### Task 1: Write and verify the failing test

**Files:**
- Create: `tests/test_bot_info_tool.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_bot_info_tool.py` with the following content:

```python
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
```

- [ ] **Step 2: Run to verify the tests fail**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python -m pytest tests/test_bot_info_tool.py -v 2>&1 | head -40
```

Expected: `ModuleNotFoundError: No module named 'llm.tools.bot_info'` or similar import failure — confirms the file doesn't exist yet.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_bot_info_tool.py
git commit -m "test: add failing tests for BotInfoTools (get_bot_changelog)"
```

---

### Task 2: Implement `llm/tools/bot_info.py`

**Files:**
- Create: `llm/tools/bot_info.py`

- [ ] **Step 1: Create the implementation**

Create `llm/tools/bot_info.py` with the following content:

```python
"""Bot info tools for LLM integration.

Provides a tool for the AI agent to query the bot's own GitHub release
history to answer questions about recent updates and changelog.
All tools are routed to the info_agent via target_agent_mode = "info".
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools.structured import StructuredTool

from addons.logging import get_logger
from addons.settings import update_config
from addons.update.checker import VersionChecker

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

_logger = get_logger(server_id="Bot", source="llm.tools.bot_info")


class BotInfoTools:
    """Container for bot self-information tools."""

    def __init__(self, runtime: "OrchestratorRequest") -> None:
        self.runtime = runtime
        self.logger = getattr(runtime, "logger", _logger)

    def get_tools(self) -> list:
        """Return bot info tools."""
        logger = self.logger

        async def get_bot_changelog() -> str:
            """Fetches the bot's latest GitHub release notes to show recent updates.

            Returns the current version, latest version, whether an update is
            available, the release notes, and the published date.
            Use when the user asks what the bot was recently updated with.
            """
            try:
                checker = VersionChecker(github_config=update_config.github)
                info = await checker.check_for_updates()

                if "error" in info:
                    return f"無法取得更新資訊：{info['error']}"

                current = info.get("current_version", "unknown")
                latest = info.get("latest_version", "unknown")
                update_available = info.get("update_available", False)
                notes = info.get("release_notes", "").strip()
                published = info.get("published_at", "")[:10]  # YYYY-MM-DD

                lines = [
                    f"## 機器人版本資訊",
                    f"- 目前版本：{current}",
                    f"- 最新版本：{latest}",
                    f"- 有新版本可用：{'是' if update_available else '否'}",
                ]
                if published:
                    lines.append(f"- 發布日期：{published}")
                if notes:
                    lines.append(f"\n### 更新內容\n{notes}")
                else:
                    lines.append("\n（無更新說明）")

                return "\n".join(lines)

            except Exception as e:
                logger.warning(f"get_bot_changelog failed: {e}")
                return f"取得版本資訊時發生錯誤：{e}"

        _info_meta = {"target_agent_mode": "info"}
        return [
            StructuredTool.from_function(
                func=None,
                name="get_bot_changelog",
                metadata=_info_meta,
                coroutine=get_bot_changelog,
                description=get_bot_changelog.__doc__,
            )
        ]
```

- [ ] **Step 2: Run the tests**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python -m pytest tests/test_bot_info_tool.py -v
```

Expected: All 7 tests pass.

- [ ] **Step 3: Commit the implementation**

```bash
git add llm/tools/bot_info.py
git commit -m "feat: add get_bot_changelog tool wrapping VersionChecker"
```

---

### Task 3: Verify auto-discovery integration

**Files:**
- No new files — verify `tools_factory.py` auto-discovers the new module.

- [ ] **Step 1: Confirm the tool appears in the factory's discovery**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python -c "
import sys, types
from pathlib import Path

# Minimal stubs so tools_factory can import
class _L:
    def info(self,*a,**kw): pass
    def warning(self,*a,**kw): pass
    def error(self,*a,**kw): pass
    def debug(self,*a,**kw): pass

import addons.logging, addons.settings
# Just print discovered module names from llm/tools/
import pkgutil, importlib
pkg = importlib.import_module('llm.tools')
names = [name for _, name, _ in pkgutil.iter_modules(pkg.__path__)]
print('Discovered modules:', names)
assert 'bot_info' in names, 'bot_info NOT found!'
print('OK: bot_info is discovered')
"
```

Expected output includes `bot_info` in the list and prints `OK: bot_info is discovered`.

- [ ] **Step 2: Commit verification note**

No code change needed. If the assertion above passes, the factory will auto-discover `BotInfoTools` at runtime.

```bash
git commit --allow-empty -m "chore: verify bot_info auto-discovery (no code change)"
```
