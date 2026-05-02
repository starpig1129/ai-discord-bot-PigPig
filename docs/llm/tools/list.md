# Available LLM Tools Reference

This list contains all the tools available to the PigPig Bot's LLM agents. Each tool is designed to perform a specific action and return a string result.

## Information & Search

| Tool Name | Module | Description |
|-----------|--------|-------------|
| `internet_search` | `internet_search.py` | Performs web, YouTube, or food searches with Gemini grounding support. |
| `get_user_info` | `user_data.py` | Retrieves biological info and saved instructions for a user. |
| `save_user_info` | `user_data.py` | Updates the bot's permanent memory about a user. |
| `search_episodic_memory` | `episodic_memory.py` | Manually triggers a semantic search on past conversations. |
| `get_user_stats` | `user_stats.py` | Retrieves activity statistics and sends a word cloud image. |
| `get_server_context` | `server_context.py` | Retrieves name, members, roles, and channels of the server. |
| `get_channel_context` | `server_context.py` | Retrieves detailed information about a specific channel. |
| `get_user_discord_info`| `server_context.py` | Retrieves a member's Discord profile, roles, and current activity. |
| `get_channel_participants` | `user_activity.py` | Lists active users in the current channel (voice or text). |

## Knowledge Management

| Tool Name | Module | Description |
|-----------|--------|-------------|
| `update_guild_knowledge` | `knowledge.py` | Records or updates facts, memes, or culture for the entire server. |
| `update_channel_knowledge`| `knowledge.py` | Records or updates facts or culture for the current channel only. |

## Discord Interaction

| Tool Name | Module | Description |
|-----------|--------|-------------|
| `get_guild_emojis` | `interaction_tools.py` | Lists custom emojis available in the current server. |
| `add_reaction` | `interaction_tools.py` | Adds an emoji reaction to a specific message. |
| `get_guild_stickers` | `interaction_tools.py` | Lists stickers available in the current server. |
| `send_sticker` | `interaction_tools.py` | Sends a specific sticker to the channel. |
| `change_own_nickname` | `interaction_tools.py` | Changes the bot's local nickname for roleplay. |
| `dramatic_pause` | `interaction_tools.py` | Pauses briefly while showing the "typing..." indicator. |
| `delete_own_last_message` | `interaction_tools.py` | Deletes the bot's most recent message in the channel. |

## Utilities & Actions

| Tool Name | Module | Description |
|-----------|--------|-------------|
| `set_reminder` | `reminder.py` | Sets a timer or reminder for a specific user. |
| `calculate_math` | `math.py` | Performs mathematical calculations and expression evaluation. |
| `generate_image` | `image.py` | Generates images based on text prompts using AI providers. |
| `get_bot_changelog` | `bot_info.py` | Returns technical specs, version info, and bot status. |

## Discovery

| Tool Name | Module | Description |
|-----------|--------|-------------|
| `list_tools` | `tools_overview.py` | Dynamically lists all currently loaded tools and their signatures. |

## Tool Constraints

- **Character Limits**: Tool outputs are typically truncated to 1000-2000 characters to prevent prompt overflow.
- **Permission Awareness**: Certain tools (like admin-only actions) are filtered out by the `ToolsFactory` if the user lacks the required Discord permissions.
- **Agent Mode**: 
  - **Info Mode**: Tools focused on gathering data (Search, Memory).
  - **Message Mode**: Tools focused on taking actions (Reminders, Reactions).
- **Safe Execution**: All tools are executed within an async environment with centralized error reporting via `func.report_error`.

---
*The LLM "Info Agent" typically uses these tools to gather context before the "Message Agent" formulates the final reply.*
