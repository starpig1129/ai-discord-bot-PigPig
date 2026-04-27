# Bot Changelog Tool — Design Spec

**Date:** 2026-04-27  
**Status:** Approved

## Goal

Add a LangChain tool that lets the bot answer questions like "你最近更新了什麼？" by fetching its own release notes from GitHub.

## Chosen Approach

Wrap the existing `VersionChecker` (Approach A). No new HTTP logic; reuse what already exists.

## New File

`llm/tools/bot_info.py`

## Architecture

### Class: `BotInfoTools`

Follows the project-standard `*Tools` pattern:

```
BotInfoTools(runtime: OrchestratorRequest)
  └── get_tools() → [get_bot_changelog]
```

- Constructor accepts `runtime` (may be unused, kept for consistency with the pattern).
- `get_tools()` returns a single async LangChain `@tool`.

### Tool: `get_bot_changelog`

**Target agent:** `info` (tagged via `metadata["target_agent_mode"] = "info"`)

**What it does:**

1. Instantiate `VersionChecker` with `update_config.github` (falls back to empty dict, which uses the hardcoded default GitHub API URL).
2. Await `checker.check_for_updates()`.
3. Format and return a string with:
   - Current version
   - Latest version
   - Whether an update is available
   - Release notes (`body` from GitHub)
   - Published date

**Error handling:** If `check_for_updates()` raises or returns an `"error"` key, return a human-readable error string instead of raising.

## Integration

No changes to `tools_factory.py` or `orchestrator.py` are needed — the factory auto-discovers all `*Tools` classes in `llm/tools/`.

## Data Flow

```
info_agent calls get_bot_changelog
  → VersionChecker(update_config.github).check_for_updates()
  → GitHub API: /repos/starpig1129/ai-discord-bot-PigPig/releases/latest
  → returns formatted string with version + release notes
```

## Out of Scope

- Fetching multiple releases (only latest)
- Triggering an update from this tool
- Caching the API response
