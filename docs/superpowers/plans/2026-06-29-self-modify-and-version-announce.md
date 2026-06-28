# Self-Modification & Version Announcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two features: (1) the bot modifies its own system prompt via a LangChain tool in a single model call, and (2) the bot auto-announces new features on the first guild message after each version update.

**Architecture:** Feature 1 adds a `SystemPromptTools` class under `llm/tools/` following the existing `XxxTools + get_tools()` pattern; the LLM generates a merged prompt as a tool argument, so no multi-step read-merge-write loop is needed. Feature 2 stores a per-guild `seen_version` in SQLite, passes an `announce_new_version` flag into `handle_message`, and appends a one-time instruction to the message-agent system prompt so the LLM calls the existing `get_bot_changelog` tool.

**Tech Stack:** Python 3.11+, discord.py, LangChain (`langchain_core.tools.structured.StructuredTool`), SQLite3, pytest + pytest-asyncio

## Global Constraints

- All function signatures must include full type hints.
- Every public class/function must have a Google-style docstring.
- No silent failures: raise exceptions at system boundaries; only return error strings inside LangChain tools (the LLM needs readable feedback, not exceptions).
- Logs via `get_logger(server_id=..., source=__name__)` — never stdlib `logging`.
- Tests go in `tests/` at project root. Follow the stub pattern in `tests/test_bot_info_tool.py` (pre-stub heavy deps before importing the module under test).
- Run tests with: `cd <project_root> && python -m pytest tests/<file> -v`

---

## File Map

### New Files
| File | Responsibility |
|---|---|
| `llm/tools/system_prompt_tools.py` | `SystemPromptTools` class + `write_personality` shared helper |
| `cogs/memory/db/version_storage.py` | `GuildVersionStorage` — per-guild seen-version tracking |
| `tests/test_system_prompt_tools.py` | Tests for `SystemPromptTools.update_personality` |
| `tests/test_version_storage.py` | Tests for `GuildVersionStorage` |

### Modified Files
| File | Change |
|---|---|
| `base_configs/prompt/message_agent.yaml` | Add `personality_modification` guidance module |
| `cogs/memory/db/schema.py` | Add `guild_version_seen` table in `create_tables()` |
| `llm/schema.py` | Add `announce_new_version: bool = False` to `OrchestratorRequest` |
| `llm/orchestrator.py` | Accept + inject `announce_new_version` in `handle_message` |
| `llm/tools/bot_info.py` | Change `target_agent_mode` from `"info"` to `"all"` |
| `bot.py` | Init `GuildVersionStorage`; version check before orchestrator call; write-back after success |
| `cogs/system_prompt/commands.py` | Add `/set_personality` app command |

---

## Task 1: `llm/tools/system_prompt_tools.py` — update_personality tool

**Files:**
- Create: `llm/tools/system_prompt_tools.py`
- Test: `tests/test_system_prompt_tools.py`

**Interfaces:**
- Produces:
  - `write_personality(guild_id: str, channel_id: str, merged_prompt: str, scope: str, bot: Any, user_id: str) -> str` (exported via `__all__`)
  - `SystemPromptTools(runtime: OrchestratorRequest)` with `.get_tools() -> list` returning one `StructuredTool` named `"update_personality"`

- [ ] **Step 1: Write failing tests**

Create `tests/test_system_prompt_tools.py`:

```python
"""Tests for llm/tools/system_prompt_tools.py."""
import sys
import types
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# ── Stub heavy dependencies ──────────────────────────────────────────────────

class _DummyLogger:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def debug(self, *a, **kw): pass
    def bind(self, **kw): return self

fake_addons = types.ModuleType("addons")
fake_addons.__path__ = [str(project_root / "addons")]
fake_logging_mod = types.ModuleType("addons.logging")
fake_logging_mod.get_logger = lambda **kwargs: _DummyLogger()
fake_settings_mod = types.ModuleType("addons.settings")
fake_settings_mod.update_config = types.SimpleNamespace(github={})
fake_addons.logging = fake_logging_mod
fake_addons.settings = fake_settings_mod
sys.modules.setdefault("addons", fake_addons)
sys.modules.setdefault("addons.logging", fake_logging_mod)
sys.modules.setdefault("addons.settings", fake_settings_mod)

fake_function = types.ModuleType("function")
fake_function.func = types.SimpleNamespace(report_error=AsyncMock(return_value=None))
sys.modules.setdefault("function", fake_function)

# Stub langchain_core
fake_lc = types.ModuleType("langchain_core")
fake_lc.__path__ = []
fake_tools = types.ModuleType("langchain_core.tools")
fake_tools.__path__ = []
fake_structured = types.ModuleType("langchain_core.tools.structured")

class _FakeStructuredTool:
    def __init__(self, name, coroutine, description, metadata):
        self.name = name
        self.coroutine = coroutine
        self.description = description
        self.metadata = metadata or {}

    @classmethod
    def from_function(cls, func, name, coroutine, description, metadata=None):
        return cls(name=name, coroutine=coroutine, description=description, metadata=metadata)

fake_structured.StructuredTool = _FakeStructuredTool
sys.modules.setdefault("langchain_core", fake_lc)
sys.modules.setdefault("langchain_core.tools", fake_tools)
sys.modules.setdefault("langchain_core.tools.structured", fake_structured)

# Stub cogs.system_prompt.permissions
fake_cogs = types.ModuleType("cogs")
fake_cogs.__path__ = []
fake_sp = types.ModuleType("cogs.system_prompt")
fake_sp.__path__ = []
fake_perm_mod = types.ModuleType("cogs.system_prompt.permissions")

class FakePermissionValidator:
    def __init__(self, bot): pass
    def can_modify_server_prompt(self, user, guild, config=None): return False
    def can_modify_channel_prompt(self, user, channel, config=None): return True

fake_perm_mod.PermissionValidator = FakePermissionValidator
fake_sp.permissions = fake_perm_mod

fake_sp_exc = types.ModuleType("cogs.system_prompt.exceptions")
class _FakeContentTooLongError(Exception): pass
class _FakeUnsafeContentError(Exception): pass
fake_sp_exc.ContentTooLongError = _FakeContentTooLongError
fake_sp_exc.UnsafeContentError = _FakeUnsafeContentError

sys.modules.setdefault("cogs", fake_cogs)
sys.modules.setdefault("cogs.system_prompt", fake_sp)
sys.modules.setdefault("cogs.system_prompt.permissions", fake_perm_mod)
sys.modules.setdefault("cogs.system_prompt.exceptions", fake_sp_exc)

# Now safe to import
from llm.tools.system_prompt_tools import SystemPromptTools, write_personality  # noqa: E402


def _make_runtime(guild_id=111, channel_id=222, author_id=333, bot=None):
    msg = MagicMock()
    msg.guild.id = guild_id
    msg.channel.id = channel_id
    msg.author.id = author_id
    runtime = MagicMock()
    runtime.message = msg
    runtime.bot = bot or MagicMock()
    return runtime


def _make_bot_with_manager(set_channel_return=True, set_server_return=True):
    mock_manager = MagicMock()
    mock_manager.set_channel_prompt.return_value = set_channel_return
    mock_manager.set_server_prompt.return_value = set_server_return
    mock_manager.cache = MagicMock()
    mock_cog = MagicMock()
    mock_cog.get_system_prompt_manager.return_value = mock_manager
    mock_bot = MagicMock()
    mock_bot.get_cog.return_value = mock_cog
    return mock_bot, mock_manager


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_get_tools_returns_one_tool():
    """SystemPromptTools.get_tools returns exactly one tool named update_personality."""
    runtime = _make_runtime()
    tools = SystemPromptTools(runtime).get_tools()
    assert len(tools) == 1
    assert tools[0].name == "update_personality"


def test_tool_target_agent_mode_is_message():
    """update_personality tool has target_agent_mode=message in metadata."""
    runtime = _make_runtime()
    tool = SystemPromptTools(runtime).get_tools()[0]
    assert tool.metadata.get("target_agent_mode") == "message"


def test_write_personality_exported():
    """write_personality is exported from the module."""
    import llm.tools.system_prompt_tools as mod
    assert "write_personality" in mod.__all__
    assert "SystemPromptTools" in mod.__all__


class TestUpdatePersonalityChannel:
    def setup_method(self):
        self.mock_bot, self.mock_manager = _make_bot_with_manager()
        self.runtime = _make_runtime(bot=self.mock_bot)
        self.tool = SystemPromptTools(self.runtime).get_tools()[0]

    def test_calls_set_channel_prompt_with_correct_args(self):
        asyncio.get_event_loop().run_until_complete(
            self.tool.coroutine(merged_prompt="Be funny.", scope="channel")
        )
        self.mock_manager.set_channel_prompt.assert_called_once_with(
            "111", "222", {"prompt": "Be funny.", "enabled": True}, "333"
        )

    def test_returns_success_message(self):
        result = asyncio.get_event_loop().run_until_complete(
            self.tool.coroutine(merged_prompt="Be funny.", scope="channel")
        )
        assert "success" in result.lower() or "updated" in result.lower()

    def test_invalidates_cache_after_write(self):
        asyncio.get_event_loop().run_until_complete(
            self.tool.coroutine(merged_prompt="Be funny.", scope="channel")
        )
        self.mock_manager.cache.invalidate.assert_called()


class TestUpdatePersonalityServer:
    def setup_method(self):
        self.mock_bot, self.mock_manager = _make_bot_with_manager()
        self.runtime = _make_runtime(bot=self.mock_bot)
        self.tool = SystemPromptTools(self.runtime).get_tools()[0]

    def test_blocks_non_admin_from_server_scope(self):
        with patch("cogs.system_prompt.permissions.PermissionValidator") as MockV:
            MockV.return_value.can_modify_server_prompt.return_value = False
            result = asyncio.get_event_loop().run_until_complete(
                self.tool.coroutine(merged_prompt="...", scope="server")
            )
        assert "permission" in result.lower() or "administrator" in result.lower()

    def test_allows_admin_to_set_server_scope(self):
        with patch("cogs.system_prompt.permissions.PermissionValidator") as MockV:
            MockV.return_value.can_modify_server_prompt.return_value = True
            result = asyncio.get_event_loop().run_until_complete(
                self.tool.coroutine(merged_prompt="Be formal.", scope="server")
            )
        self.mock_manager.set_server_prompt.assert_called_once_with(
            "111", {"prompt": "Be formal.", "enabled": True}, "333"
        )
        assert "success" in result.lower() or "updated" in result.lower()


class TestUpdatePersonalityErrors:
    def test_missing_cog_returns_error_string(self):
        mock_bot = MagicMock()
        mock_bot.get_cog.return_value = None
        runtime = _make_runtime(bot=mock_bot)
        tool = SystemPromptTools(runtime).get_tools()[0]
        result = asyncio.get_event_loop().run_until_complete(
            tool.coroutine(merged_prompt="...", scope="channel")
        )
        assert "error" in result.lower()

    def test_no_message_context_returns_error_string(self):
        runtime = MagicMock()
        runtime.message = None
        tool = SystemPromptTools(runtime).get_tools()[0]
        result = asyncio.get_event_loop().run_until_complete(
            tool.coroutine(merged_prompt="...", scope="channel")
        )
        assert "error" in result.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python -m pytest tests/test_system_prompt_tools.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm.tools.system_prompt_tools'`

- [ ] **Step 3: Implement `llm/tools/system_prompt_tools.py`**

```python
"""LangChain tool for the bot to modify its own system prompt.

The LLM reads its current personality from the system-prompt context it
already has, generates a merged version, and calls this tool to write it.
Only the write side lives here — no extra LLM call is needed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.tools.structured import StructuredTool

from addons.logging import get_logger

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

_logger = get_logger(server_id="Bot", source="llm.tools.system_prompt_tools")

__all__ = ["write_personality", "SystemPromptTools"]


async def write_personality(
    guild_id: str,
    channel_id: str,
    merged_prompt: str,
    scope: str,
    bot: Any,
    user_id: str,
) -> str:
    """Write a merged personality string to the system prompt store.

    Args:
        guild_id: Discord guild ID string.
        channel_id: Discord channel ID string.
        merged_prompt: The complete merged system prompt text.
        scope: "channel" or "server".
        bot: The discord.ext.commands.Bot instance.
        user_id: ID of the user requesting the change (for audit).

    Returns:
        A human-readable confirmation or error string.
    """
    from cogs.system_prompt.exceptions import ContentTooLongError, UnsafeContentError

    cog = bot.get_cog("SystemPromptManagerCog")
    if cog is None:
        return "Error: SystemPromptManagerCog is not loaded. Cannot save personality."

    manager = cog.get_system_prompt_manager()
    prompt_data: dict[str, Any] = {"prompt": merged_prompt, "enabled": True}

    try:
        if scope == "server":
            manager.set_server_prompt(guild_id, prompt_data, user_id)
            manager.cache.invalidate(guild_id)
            return "Personality updated successfully for the entire server."
        else:
            manager.set_channel_prompt(guild_id, channel_id, prompt_data, user_id)
            manager.cache.invalidate(guild_id, channel_id)
            return "Personality updated successfully for this channel."
    except ContentTooLongError as exc:
        return f"Error: The prompt is too long ({exc}). Please shorten your description."
    except UnsafeContentError as exc:
        return f"Error: The prompt contains unsafe content ({exc}). Please revise."
    except Exception as exc:
        _logger.error(f"write_personality failed: {exc}")
        return f"Error saving personality: {exc}"


class SystemPromptTools:
    """Container for the bot's self-modification tool."""

    def __init__(self, runtime: "OrchestratorRequest") -> None:
        """Initialize with the orchestrator runtime context.

        Args:
            runtime: The current OrchestratorRequest context.
        """
        self.runtime = runtime
        self.logger = getattr(runtime, "logger", _logger)

    def get_tools(self) -> list:
        """Return the list of self-modification tools.

        Returns:
            List containing the update_personality StructuredTool.
        """
        runtime = self.runtime

        async def update_personality(merged_prompt: str, scope: str = "channel") -> str:
            """Modify the bot's personality or system prompt for this channel or server.

            You already know your current personality from the system prompt in your
            context. Generate a COMPLETE merged version incorporating the user's
            requested changes (do not just write the delta), then call this tool.

            Args:
                merged_prompt: The complete merged system prompt text — your current
                    personality with the requested changes incorporated. Must be a
                    full system prompt, not just the changed part.
                scope: "channel" applies only to the current channel (any user may
                    do this). "server" applies to the entire server (admin only).

            Returns:
                Confirmation message or an error description.
            """
            message = getattr(runtime, "message", None)
            if message is None:
                return "Error: No message context available."

            guild = getattr(message, "guild", None)
            channel = getattr(message, "channel", None)
            author = getattr(message, "author", None)

            if guild is None or channel is None or author is None:
                return "Error: Cannot determine guild, channel, or author."

            guild_id = str(guild.id)
            channel_id = str(channel.id)
            user_id = str(author.id)
            bot = getattr(runtime, "bot", None)

            if scope == "server":
                from cogs.system_prompt.permissions import PermissionValidator
                validator = PermissionValidator(bot)
                if not validator.can_modify_server_prompt(author, guild):
                    return (
                        "Error: You need administrator permissions to modify the "
                        "server-level personality."
                    )

            return await write_personality(guild_id, channel_id, merged_prompt, scope, bot, user_id)

        _message_meta: dict[str, str] = {"target_agent_mode": "message"}
        return [
            StructuredTool.from_function(
                func=None,
                name="update_personality",
                metadata=_message_meta,
                coroutine=update_personality,
                description=update_personality.__doc__,
            )
        ]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_system_prompt_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add llm/tools/system_prompt_tools.py tests/test_system_prompt_tools.py
git commit -m "feat: add update_personality tool for bot self-modification"
```

---

## Task 2: Add personality-modification guidance to `message_agent.yaml`

**Files:**
- Modify: `base_configs/prompt/message_agent.yaml`

**Interfaces:**
- Produces: a `personality_modification` module section that `ProtectedPromptManager` will load alongside other modules.

- [ ] **Step 1: Open `base_configs/prompt/message_agent.yaml` and locate the end of the modules list**

The file ends after the last module (e.g., `reminders`). Add the following new section at the end, before any trailing newline:

```yaml
# ============================================
# PERSONALITY MODIFICATION
# ============================================
personality_modification:
  description: "Instructions for self-modifying personality via tool call"
  content: |
    ## Personality Modification

    If a user asks you to adjust your personality, speaking style, tone, background,
    or any aspect of how you present yourself, follow these steps in a single response:

    1. You already know your current personality from this system prompt. Read it carefully.
    2. Generate a COMPLETE merged version of the system prompt that incorporates the
       requested change (not just the delta — write the full prompt).
    3. Call `update_personality` with the full merged text and the appropriate scope:
       - `scope="channel"` — applies only to the current channel (any user may do this).
       - `scope="server"` — applies to the entire server (requires admin permission).
    4. Confirm to the user that the update has been applied.

    Do not ask for confirmation before calling the tool unless the request is ambiguous.
    After saving, briefly describe what you changed.
```

- [ ] **Step 2: Verify YAML parses without errors**

```bash
python -c "
import yaml
with open('base_configs/prompt/message_agent.yaml') as f:
    data = yaml.safe_load(f)
assert 'personality_modification' in data, 'section missing'
print('OK:', list(data.keys()))
"
```

Expected output includes `personality_modification` in the key list.

- [ ] **Step 3: Commit**

```bash
git add base_configs/prompt/message_agent.yaml
git commit -m "feat: add personality modification guidance to message_agent prompt"
```

---

## Task 3: `/set_personality` slash command in `commands.py`

**Files:**
- Modify: `cogs/system_prompt/commands.py`

**Interfaces:**
- Consumes: `write_personality` from `llm.tools.system_prompt_tools`
- Consumes: `SystemPromptManager.get_effective_prompt(channel_id, guild_id, message)` to read existing prompt
- Consumes: `ModelManager.get_model_priority_list("message_model")` + `create_model_instance` to call LLM for merge
- Produces: `/set_personality scope description` app command registered on `SystemPromptCommands` cog

- [ ] **Step 1: Add the slash command to `SystemPromptCommands` class**

Open `cogs/system_prompt/commands.py` and add the following inside the `SystemPromptCommands(commands.Cog)` class, after the last existing app command method:

```python
    @app_commands.command(
        name="set_personality",
        description="Adjust the bot's personality or speaking style for this channel or server."
    )
    @app_commands.describe(
        scope="'channel' for current channel only, 'server' for entire server (admin only)",
        description="Natural language description of how you want to adjust the bot's personality"
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name="channel", value="channel"),
        app_commands.Choice(name="server", value="server"),
    ])
    @handle_system_prompt_error
    async def set_personality(
        self,
        interaction: discord.Interaction,
        scope: app_commands.Choice[str],
        description: str,
    ) -> None:
        """Slash command: adjust bot personality via natural language description.

        Args:
            interaction: The Discord interaction object.
            scope: Choice of "channel" or "server".
            description: Natural language description of the desired personality change.
        """
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)
        channel_id = str(interaction.channel.id)
        user_id = str(interaction.user.id)
        scope_value = scope.value

        # Permission check for server scope
        if scope_value == "server":
            from .permissions import PermissionValidator
            validator = PermissionValidator(self.bot)
            if not validator.can_modify_server_prompt(interaction.user, interaction.guild):
                await interaction.followup.send(
                    "❌ You need administrator permissions to modify the server-level personality.",
                    ephemeral=True,
                )
                return

        # Get current effective system prompt to merge with
        sp_cog = self.bot.get_cog("SystemPromptManagerCog")
        if sp_cog is None:
            await interaction.followup.send("❌ System prompt module is not loaded.", ephemeral=True)
            return

        manager = sp_cog.get_system_prompt_manager()
        current_prompt_data = manager.get_effective_prompt(channel_id, guild_id)
        current_prompt = current_prompt_data.get("prompt", "")

        # Ask LLM to produce merged prompt
        from llm.model_manager import ModelManager
        from llm.utils.model_init import create_model_instance

        model_manager = ModelManager()
        try:
            model_priority = model_manager.get_model_priority_list("message_model")
            model_instance = create_model_instance(model_priority[0], max_retries=1)
        except Exception as exc:
            await interaction.followup.send(f"❌ Failed to load language model: {exc}", ephemeral=True)
            return

        merge_prompt = (
            f"You are a system prompt editor. The current system prompt is:\n\n"
            f"---\n{current_prompt}\n---\n\n"
            f"The user wants to change the personality as follows: {description}\n\n"
            f"Output ONLY the complete updated system prompt with the change incorporated. "
            f"Do not add any commentary, preamble, or explanation — just the prompt text."
        )

        from langchain_core.messages import HumanMessage
        try:
            response = await model_instance.ainvoke([HumanMessage(content=merge_prompt)])
            merged_prompt = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            await interaction.followup.send(f"❌ Failed to generate merged prompt: {exc}", ephemeral=True)
            return

        # Write using shared helper
        from llm.tools.system_prompt_tools import write_personality
        result = await write_personality(
            guild_id=guild_id,
            channel_id=channel_id,
            merged_prompt=merged_prompt,
            scope=scope_value,
            bot=self.bot,
            user_id=user_id,
        )

        if result.startswith("Error"):
            await interaction.followup.send(f"❌ {result}", ephemeral=True)
        else:
            await interaction.followup.send(
                f"✅ {result}\n\nApplied change: *{description}*",
                ephemeral=True,
            )
```

- [ ] **Step 2: Verify the file has no syntax errors**

```bash
python -c "import ast; ast.parse(open('cogs/system_prompt/commands.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add cogs/system_prompt/commands.py
git commit -m "feat: add /set_personality slash command"
```

---

## Task 4: `guild_version_seen` table schema

**Files:**
- Modify: `cogs/memory/db/schema.py`

**Interfaces:**
- Produces: `guild_version_seen` table created by the existing `create_tables(conn)` function.

- [ ] **Step 1: Write failing test**

Create `tests/test_version_storage.py` (partial — only schema part first):

```python
"""Tests for GuildVersionStorage and guild_version_seen schema."""
import sqlite3
import sys
import types
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Stub addons.logging before importing schema
import addons.settings  # noqa: F401 — pre-cache real settings (from conftest pattern)

class _DummyLogger:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def debug(self, *a, **kw): pass

import addons.logging as _al
_orig_get_logger = _al.get_logger
_al.get_logger = lambda **kwargs: _DummyLogger()


def _in_memory_conn() -> sqlite3.Connection:
    return sqlite3.connect(":memory:")


def test_create_tables_creates_guild_version_seen():
    """create_tables must create the guild_version_seen table."""
    from cogs.memory.db.schema import create_tables
    conn = _in_memory_conn()
    create_tables(conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='guild_version_seen'"
    )
    assert cursor.fetchone() is not None, "guild_version_seen table was not created"
    conn.close()


def test_guild_version_seen_has_correct_columns():
    """guild_version_seen must have guild_id, seen_version, seen_at columns."""
    from cogs.memory.db.schema import create_tables
    conn = _in_memory_conn()
    create_tables(conn)
    cursor = conn.execute("PRAGMA table_info(guild_version_seen)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "guild_id" in columns
    assert "seen_version" in columns
    assert "seen_at" in columns
    conn.close()
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/test_version_storage.py::test_create_tables_creates_guild_version_seen -v
```

Expected: FAIL — `AssertionError: guild_version_seen table was not created`

- [ ] **Step 3: Add `guild_version_seen` table to `create_tables()` in `cogs/memory/db/schema.py`**

Find the end of `create_tables()` (just before `conn.commit()` or the final closing logic) and add:

```python
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_version_seen (
            guild_id     TEXT PRIMARY KEY,
            seen_version TEXT NOT NULL,
            seen_at      REAL NOT NULL
        );
        """
    )
```

- [ ] **Step 4: Run schema tests to confirm they pass**

```bash
python -m pytest tests/test_version_storage.py::test_create_tables_creates_guild_version_seen tests/test_version_storage.py::test_guild_version_seen_has_correct_columns -v
```

Expected: both PASS

- [ ] **Step 5: Commit**

```bash
git add cogs/memory/db/schema.py
git commit -m "feat: add guild_version_seen table to SQLite schema"
```

---

## Task 5: `cogs/memory/db/version_storage.py` — GuildVersionStorage

**Files:**
- Create: `cogs/memory/db/version_storage.py`
- Test: `tests/test_version_storage.py` (add to existing file from Task 4)

**Interfaces:**
- Produces: `GuildVersionStorage(db_path: Union[str, Path])` with:
  - `.get_seen_version(guild_id: str) -> Optional[str]`
  - `.set_seen_version(guild_id: str, version: str) -> None`

- [ ] **Step 1: Add failing tests to `tests/test_version_storage.py`**

Append to the existing test file:

```python
import time
from typing import Optional
from unittest.mock import patch


class TestGuildVersionStorage:
    """Integration tests using an in-memory SQLite database."""

    def setup_method(self):
        from cogs.memory.db.schema import create_tables
        self.conn = sqlite3.connect(":memory:")
        create_tables(self.conn)
        # Patch DatabaseConnection to return our in-memory conn
        import cogs.memory.db.version_storage as vs_mod
        self._patcher = patch.object(
            vs_mod.GuildVersionStorage, "_open_connection",
            return_value=self.conn,
        )
        self._patcher.start()
        from cogs.memory.db.version_storage import GuildVersionStorage
        self.storage = GuildVersionStorage(":memory:")

    def teardown_method(self):
        self._patcher.stop()
        self.conn.close()

    def test_get_seen_version_returns_none_for_unknown_guild(self):
        result = self.storage.get_seen_version("guild_xyz")
        assert result is None

    def test_set_and_get_seen_version_roundtrip(self):
        self.storage.set_seen_version("guild_abc", "v3.2.0")
        result = self.storage.get_seen_version("guild_abc")
        assert result == "v3.2.0"

    def test_set_seen_version_updates_existing_record(self):
        self.storage.set_seen_version("guild_abc", "v3.1.0")
        self.storage.set_seen_version("guild_abc", "v3.2.0")
        result = self.storage.get_seen_version("guild_abc")
        assert result == "v3.2.0"

    def test_set_seen_version_stores_current_timestamp(self):
        before = time.time()
        self.storage.set_seen_version("guild_time", "v1.0.0")
        after = time.time()
        # Read seen_at directly
        row = self.conn.execute(
            "SELECT seen_at FROM guild_version_seen WHERE guild_id=?", ("guild_time",)
        ).fetchone()
        assert row is not None
        assert before <= row[0] <= after

    def test_multiple_guilds_are_independent(self):
        self.storage.set_seen_version("guild_1", "v3.2.0")
        self.storage.set_seen_version("guild_2", "v3.1.0")
        assert self.storage.get_seen_version("guild_1") == "v3.2.0"
        assert self.storage.get_seen_version("guild_2") == "v3.1.0"
```

- [ ] **Step 2: Run to confirm failures**

```bash
python -m pytest tests/test_version_storage.py -v -k "TestGuildVersionStorage"
```

Expected: `ImportError: cannot import name 'GuildVersionStorage'`

- [ ] **Step 3: Implement `cogs/memory/db/version_storage.py`**

```python
"""Per-guild version tracking storage.

Stores which bot version each guild has already seen, so the
version-announcement feature fires exactly once per version per guild.
"""
import sqlite3
import time
from pathlib import Path
from typing import Optional, Union

from addons.logging import get_logger
from cogs.memory.db import schema

logger = get_logger(server_id="system", source=__name__)


class GuildVersionStorage:
    """SQLite-backed store for per-guild seen-version tracking.

    Uses an isolated SQLite connection so it works regardless of whether
    the memory sub-system is enabled.
    """

    def __init__(self, db_path: Union[str, Path]) -> None:
        """Initialize and ensure the required table exists.

        Args:
            db_path: Path to the SQLite database file, or ":memory:" for tests.
        """
        self.db_path = Path(db_path) if db_path != ":memory:" else Path(":memory:")
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_table()

    def _open_connection(self) -> sqlite3.Connection:
        """Open (or reuse) the SQLite connection.

        Returns:
            An open sqlite3.Connection.
        """
        if self._conn is None:
            path_str = str(self.db_path)
            if path_str != ":memory:":
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path_str, check_same_thread=False)
        return self._conn

    def _ensure_table(self) -> None:
        """Create the guild_version_seen table if it does not exist."""
        conn = self._open_connection()
        schema.create_tables(conn)
        conn.commit()

    def get_seen_version(self, guild_id: str) -> Optional[str]:
        """Return the last seen bot version for a guild, or None if not recorded.

        Args:
            guild_id: Discord guild ID as a string.

        Returns:
            Version string (e.g. "v3.2.0") or None.
        """
        try:
            conn = self._open_connection()
            row = conn.execute(
                "SELECT seen_version FROM guild_version_seen WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
            return row[0] if row else None
        except Exception as exc:
            logger.error(f"get_seen_version failed for guild {guild_id}: {exc}")
            return None

    def set_seen_version(self, guild_id: str, version: str) -> None:
        """Record that guild_id has seen the given bot version.

        Args:
            guild_id: Discord guild ID as a string.
            version: Bot version string (e.g. "v3.2.0").

        Raises:
            sqlite3.Error: On database write failure.
        """
        conn = self._open_connection()
        conn.execute(
            """
            INSERT INTO guild_version_seen (guild_id, seen_version, seen_at)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                seen_version = excluded.seen_version,
                seen_at      = excluded.seen_at
            """,
            (guild_id, version, time.time()),
        )
        conn.commit()
        logger.info(f"Guild {guild_id} marked as seen version {version}")
```

- [ ] **Step 4: Run all version storage tests**

```bash
python -m pytest tests/test_version_storage.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add cogs/memory/db/version_storage.py tests/test_version_storage.py
git commit -m "feat: add GuildVersionStorage for per-guild version tracking"
```

---

## Task 6: `get_bot_changelog` tool — switch to `target_agent_mode="all"`

**Files:**
- Modify: `llm/tools/bot_info.py` (line ~83)

**Interfaces:**
- Produces: `get_bot_changelog` tool available to both info and message agents.

- [ ] **Step 1: Change `target_agent_mode` in `bot_info.py`**

In `llm/tools/bot_info.py`, find:

```python
        _info_meta = {"target_agent_mode": "info"}
```

Change it to:

```python
        _info_meta = {"target_agent_mode": "all"}
```

- [ ] **Step 2: Verify existing bot_info tests still pass**

```bash
python -m pytest tests/test_bot_info_tool.py -v
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add llm/tools/bot_info.py
git commit -m "feat: make get_bot_changelog available to message agent for version announcements"
```

---

## Task 7: `llm/schema.py` + `llm/orchestrator.py` — announce_new_version injection

**Files:**
- Modify: `llm/schema.py`
- Modify: `llm/orchestrator.py`

**Interfaces:**
- Produces:
  - `OrchestratorRequest.announce_new_version: bool` (default `False`)
  - `Orchestrator.handle_message(..., announce_new_version: bool = False)` accepting the flag

- [ ] **Step 1: Add `announce_new_version` field to `OrchestratorRequest` in `llm/schema.py`**

Open `llm/schema.py`. The current `OrchestratorRequest` is:

```python
@dataclass
class OrchestratorRequest:
    bot: Any
    message: Message
    logger: Any
```

Change it to:

```python
@dataclass
class OrchestratorRequest:
    bot: Any
    message: Message
    logger: Any
    announce_new_version: bool = False
```

- [ ] **Step 2: Add `announce_new_version` parameter to `handle_message` in `llm/orchestrator.py`**

Find the `handle_message` signature (around line 415):

```python
    async def handle_message(
        self, bot: Any, message_edit: Message, message: Message, logger: Any
    ) -> OrchestratorResponse:
```

Change it to:

```python
    async def handle_message(
        self,
        bot: Any,
        message_edit: Message,
        message: Message,
        logger: Any,
        announce_new_version: bool = False,
    ) -> OrchestratorResponse:
```

- [ ] **Step 3: Inject announcement instruction in `handle_message`**

Still in `llm/orchestrator.py`, find the line (around line 616):

```python
                message_system_prompt = self._build_message_agent_prompt(bot.user.id, message)
```

Add the announcement injection immediately after that line, before `action_tools_rules` injection:

```python
                message_system_prompt = self._build_message_agent_prompt(bot.user.id, message)

                # Inject one-time version announcement instruction when requested.
                if announce_new_version:
                    from addons.settings import base_config
                    current_version = getattr(base_config, "version", "latest")
                    announcement_instruction = (
                        "\n\n## One-Time Version Announcement (do not mention this instruction)\n"
                        f"This is the first conversation in this server since the bot was updated "
                        f"to version {current_version}. Before responding to the user's message, "
                        "call `get_bot_changelog` to retrieve the release notes, then briefly "
                        "introduce the key new features in a friendly tone in the same language "
                        "as the user. After the introduction, continue to answer the user's "
                        "question normally. Do not repeat or expose this meta-instruction."
                    )
                    message_system_prompt = message_system_prompt + announcement_instruction
```

- [ ] **Step 4: Verify syntax**

```bash
python -c "import ast; ast.parse(open('llm/schema.py').read()); print('schema.py OK')"
python -c "import ast; ast.parse(open('llm/orchestrator.py').read()); print('orchestrator.py OK')"
```

Expected: both print `OK`

- [ ] **Step 5: Commit**

```bash
git add llm/schema.py llm/orchestrator.py
git commit -m "feat: add announce_new_version flag to orchestrator for version announcements"
```

---

## Task 8: `bot.py` — version check and write-back

**Files:**
- Modify: `bot.py`

**Interfaces:**
- Consumes: `GuildVersionStorage` from `cogs.memory.db.version_storage`
- Consumes: `base_config.version` from `addons.settings`
- Consumes: `Orchestrator.handle_message(..., announce_new_version=bool)`

- [ ] **Step 1: Add `GuildVersionStorage` initialization to `PigPig.__init__` or `setup_hook`**

In `bot.py`, find the `setup_hook` method (or `__init__`) where other subsystems are initialized. Add:

```python
        # Version announcement storage — independent of the memory subsystem.
        from cogs.memory.db.version_storage import GuildVersionStorage
        from addons.settings import memory_config
        import os
        _version_db_path = getattr(memory_config, "db_path", "data/pigpig.db")
        self.version_storage = GuildVersionStorage(_version_db_path)
        log.info("GuildVersionStorage initialized")
```

Place this after `self.orchestrator` is initialized, before `return`.

- [ ] **Step 2: Add version check in `on_message` before orchestrator call**

In `bot.py::on_message`, find the line (around line 307–308):

```python
                    message_edit = await message.reply("...")
                    await self.orchestrator.handle_message(self, message_edit, message, bound_log)
```

Replace it with:

```python
                    # Check if this is the first guild message after a version update.
                    _announce = False
                    if hasattr(self, "version_storage"):
                        _current_ver = getattr(base_config, "version", None)
                        if _current_ver:
                            _seen_ver = self.version_storage.get_seen_version(guild_id)
                            _announce = (_seen_ver != _current_ver)

                    message_edit = await message.reply("...")
                    await self.orchestrator.handle_message(
                        self, message_edit, message, bound_log,
                        announce_new_version=_announce,
                    )

                    # Mark guild as having seen this version only after a successful reply.
                    if _announce and hasattr(self, "version_storage"):
                        _current_ver = getattr(base_config, "version", None)
                        if _current_ver:
                            self.version_storage.set_seen_version(guild_id, _current_ver)
```

- [ ] **Step 3: Verify syntax**

```bash
python -c "import ast; ast.parse(open('bot.py').read()); print('bot.py OK')"
```

Expected: `bot.py OK`

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat: trigger version announcement on first guild message after update"
```

---

## Self-Review

### Spec Coverage

| Spec Requirement | Task |
|---|---|
| Tool `update_personality(merged_prompt, scope)` | Task 1 |
| `required_permission="admin"` for server scope | Task 1 (validator in coroutine) |
| `target_agent_mode="message"` | Task 1 |
| System prompt guidance for self-modification | Task 2 |
| `/set_personality` slash command | Task 3 |
| Shared `write_personality` helper + `__all__` export | Task 1 |
| `guild_version_seen` SQLite table | Task 4 |
| `GuildVersionStorage.get_seen_version` / `set_seen_version` | Task 5 |
| `get_bot_changelog` available to message agent | Task 6 |
| `announce_new_version` field on `OrchestratorRequest` | Task 7 |
| Announcement instruction injected in orchestrator | Task 7 |
| Version check in `bot.py::on_message` | Task 8 |
| Write-back only after successful reply | Task 8 |
| Memory-subsystem-independent storage | Task 5 (own sqlite3 conn) |
| GitHub API unavailable → LLM announces without details | No code needed; `get_bot_changelog` already returns error string, LLM handles it |

### Placeholder Scan

No TBD, TODO, or incomplete steps found.

### Type Consistency

- `write_personality(guild_id: str, channel_id: str, merged_prompt: str, scope: str, bot: Any, user_id: str) -> str` — used identically in Task 1 and Task 3. ✅
- `GuildVersionStorage.get_seen_version(guild_id: str) -> Optional[str]` — consumed in Task 8 as `self.version_storage.get_seen_version(guild_id)`. ✅
- `GuildVersionStorage.set_seen_version(guild_id: str, version: str) -> None` — consumed in Task 8. ✅
- `handle_message(..., announce_new_version: bool = False)` defined in Task 7, called in Task 8. ✅
