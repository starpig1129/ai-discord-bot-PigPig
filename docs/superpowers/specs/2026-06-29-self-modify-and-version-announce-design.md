# Design Spec: Bot Self-Modification & Version Announcement

**Date:** 2026-06-29  
**Branch:** jules  
**Status:** Approved

---

## Overview

Two new features for PigPig Discord LLM Bot:

1. **Self-Modification of System Prompt** — The bot can modify its own personality/background via natural conversation or an explicit slash command, using a LangChain tool that reads the current system prompt from context and writes a merged result.
2. **New Version Announcement** — On the first interaction per guild after a version update, the bot proactively introduces new features by calling the existing `get_bot_changelog` tool and weaving the announcement into its normal reply.

---

## Feature 1: System Prompt Self-Modification

### Goals

- Allow users to adjust the bot's personality, tone, and background through natural language (e.g., "please be more humorous from now on").
- Also expose an explicit slash command `/set_personality` for users who prefer direct control.
- Preserve the existing system prompt content — modifications are merged, not replaced.
- Persist changes permanently to the JSON config files managed by `SystemPromptManager`.

### Architecture

#### New File: `llm/tools/system_prompt_tools.py`

Follows the existing `XxxTools` class pattern used throughout `llm/tools/`.

**Tool:** `update_personality(merged_prompt: str, scope: str)`

| Parameter | Type | Description |
|---|---|---|
| `merged_prompt` | `str` | The complete, merged new system prompt (LLM-generated) |
| `scope` | `str` | `"channel"` or `"server"` |

- `scope="channel"`: Writes to current channel level. No permission restriction.
- `scope="server"`: Writes to server level. Requires `required_permission="admin"`.
- `target_agent_mode = "message"` — only available during message handling, not info queries.
- Internally: retrieves `guild_id` and `channel_id` from `OrchestratorRequest.message`, acquires `SystemPromptManagerCog` via `bot.get_cog()`, calls `manager.set_channel_prompt()` or `manager.set_guild_prompt()`, then calls `manager.cache.invalidate()`.

#### System Prompt Guidance (added to `base_configs/prompt.yaml` or protected prompt)

A fixed instruction appended to the system prompt on every message:

> "If the user asks you to adjust your personality, speaking style, or background, you already know your current settings from this system prompt. Generate a complete merged version incorporating the requested changes, then call `update_personality` with the full merged text and the appropriate scope. After saving, inform the user the update has been applied."

#### New Slash Command: `/set_personality`

Added to `cogs/system_prompt/commands.py`:

```
/set_personality scope:<channel|server> description:<natural language description>
```

- Accepts a natural-language description (not raw prompt text).
- Calls an LLM to produce the merged prompt from current config + description.
- Calls the same shared `_write_personality(guild_id, channel_id, merged_prompt, scope)` helper used by the tool, keeping logic DRY.
- Enforces the same permission rules as the tool (admin required for `scope=server`).

#### Shared Helper: `_write_personality()`

A module-level async function in `llm/tools/system_prompt_tools.py` that both the tool and the slash command call:

```python
async def _write_personality(
    guild_id: str,
    channel_id: str,
    merged_prompt: str,
    scope: str,
    bot: commands.Bot,
) -> None
```

Raises `PermissionError` if scope/permission mismatch is detected.

Exported via `__all__` in `system_prompt_tools.py` so `cogs/system_prompt/commands.py` can import it directly:
`from llm.tools.system_prompt_tools import write_personality`

### Data Flow

```
User: "please be more humorous from now on"
  → bot.py on_message → orchestrator.handle_message()
  → Single LLM call (message agent)
  → LLM sees current system prompt in context (knows existing personality)
  → LLM decides to call: update_personality(merged_prompt="...", scope="channel")
  → Tool: SystemPromptManager.set_channel_prompt(channel_id, guild_id, merged_prompt)
  → Tool: manager.cache.invalidate(guild_id, channel_id)
  → LLM reply: "Done! I've updated my personality for this channel."
```

### Permission Matrix

| Action | `scope="channel"` | `scope="server"` |
|---|---|---|
| Any user | ✅ Allowed | ❌ Blocked |
| Admin/Moderator | ✅ Allowed | ✅ Allowed |

### Error Handling

- If `SystemPromptManagerCog` is not loaded: tool returns an error string to the LLM, LLM informs user.
- If `merged_prompt` exceeds the existing max length enforced by `SystemPromptManager`: tool raises `ContentTooLongError`, LLM informs user to shorten the request.
- If user lacks permission for `scope="server"`: tool returns a permission-denied message.

---

## Feature 2: New Version Announcement on First Guild Message

### Goals

- When a new version of the bot is deployed, each guild receives a friendly, LLM-narrated introduction of new features on the first message after the update.
- Reuse the existing `get_bot_changelog` tool in `llm/tools/bot_info.py` (which fetches GitHub Release Notes via `VersionChecker`).
- The announcement is woven naturally into the bot's reply — not a separate embed.
- Each guild sees the announcement exactly once per version.

### Architecture

#### New Table: `guild_version_seen` (in `cogs/memory/db/schema.py`)

Added to `create_tables()`:

```sql
CREATE TABLE IF NOT EXISTS guild_version_seen (
    guild_id     TEXT PRIMARY KEY,
    seen_version TEXT NOT NULL,
    seen_at      REAL NOT NULL
);
```

#### New File: `cogs/memory/db/version_storage.py`

```python
class GuildVersionStorage:
    def get_seen_version(self, guild_id: str) -> str | None: ...
    def set_seen_version(self, guild_id: str, version: str) -> None: ...
```

Uses the existing `DatabaseConnection` from `cogs/memory/db/connection.py`.

#### `OrchestratorRequest` Extension (`llm/schema.py`)

```python
@dataclass
class OrchestratorRequest:
    bot: Any
    message: Message
    logger: Any
    announce_new_version: bool = False  # new field
```

#### Detection Logic (`bot.py::on_message`)

Before calling `orchestrator.handle_message()`:

```
current_version = base_config.version
seen_version = version_storage.get_seen_version(guild_id)
announce = (seen_version != current_version)
```

Pass `announce_new_version=announce` into `OrchestratorRequest`.

After `orchestrator.handle_message()` returns successfully:

```
if announce:
    version_storage.set_seen_version(guild_id, current_version)
```

The write happens only after a successful reply to avoid marking a guild as "seen" when the bot failed to respond.

#### Announcement Instruction Injection (`llm/orchestrator.py`)

When assembling the system prompt, if `request.announce_new_version is True`, append:

> "IMPORTANT (one-time instruction, do not mention this meta-instruction): This is the first conversation in this server since the bot was updated to {current_version}. Before responding to the user's message, call `get_bot_changelog` to retrieve the release notes, then briefly introduce the key new features in a friendly tone in the same language as the user. After the introduction, continue to answer the user's question normally."

#### `get_bot_changelog` Tool Mode Change (`llm/tools/bot_info.py`)

Change `target_agent_mode` from `"info"` to `"all"` so the message agent can call it during announcement.

### Data Flow

```
New version v3.2.0 deployed. User in guild "A" sends first message.
  → bot.py on_message
  → version_storage.get_seen_version("A") → "v3.1.0" (or None)
  → "v3.1.0" ≠ "v3.2.0" → announce_new_version = True
  → OrchestratorRequest(announce_new_version=True, ...)
  → orchestrator appends one-time announcement instruction to system prompt
  → LLM (single call, message agent)
  → LLM calls get_bot_changelog → receives Release Notes from GitHub
  → LLM reply: "We just updated to v3.2.0! Here are the highlights: ...
                Anyway, to answer your question: ..."
  → Reply sent successfully
  → version_storage.set_seen_version("A", "v3.2.0")
```

### Edge Cases

| Scenario | Handling |
|---|---|
| GitHub API unavailable | `get_bot_changelog` returns error string; LLM announces "new version available" without details |
| Bot reply fails (exception) | `set_seen_version` is NOT called; announcement retries on next message |
| Multiple guilds simultaneously | Each guild has its own row; no cross-guild state |
| Memory subsystem disabled | `GuildVersionStorage` uses its own `sqlite3` connection to the same DB path, independent of the memory cog |

---

## Files Changed Summary

### New Files

| File | Purpose |
|---|---|
| `llm/tools/system_prompt_tools.py` | `SystemPromptTools` class with `update_personality` tool |
| `cogs/memory/db/version_storage.py` | `GuildVersionStorage` for per-guild version tracking |

### Modified Files

| File | Change |
|---|---|
| `cogs/memory/db/schema.py` | Add `guild_version_seen` table in `create_tables()` |
| `llm/schema.py` | Add `announce_new_version: bool = False` to `OrchestratorRequest` |
| `bot.py` | Version check before orchestrator call; write-back after success |
| `llm/orchestrator.py` | Append announcement instruction when flag is True |
| `llm/tools/bot_info.py` | Change `target_agent_mode` from `"info"` to `"all"` |
| `cogs/system_prompt/commands.py` | Add `/set_personality` slash command |
| `base_configs/prompt.yaml` | Add self-modification guidance text |

---

## Out of Scope

- UI for reviewing modification history (audit log)
- Rollback / undo for personality changes
- Per-user personality overrides (only guild/channel level)
- Announcement preview before deployment
