# Available LLM Tools Reference

This list contains all the tools available to the PigPig Bot's LLM agents. Each tool is designed to perform a specific action and return a string result.

## Information & Search

| Tool Name | Module | Description |
|-----------|--------|-------------|
| `google_search` | `internet_search.py` | Performs a Google search to find up-to-date information. |
| `youtube_search` | `internet_search.py` | Searches for videos and retrieves metadata. |
| `wikipedia_search` | `internet_search.py` | Fetches summaries from Wikipedia. |

## Internal Context & Memory

| Tool Name | Module | Description |
|-----------|--------|-------------|
| `get_user_info` | `user_data.py` | Retrieves biological info and saved instructions for a user. |
| `save_user_info` | `user_data.py` | Updates the bot's permanent memory about a user. |
| `search_memories` | `episodic_memory.py` | Manually triggers a semantic search on past conversations. |
| `get_user_activity` | `user_activity.py` | Retrieves interaction statistics (message counts, etc.). |
| `get_server_context` | `server_context.py` | Retrieves rules and knowledge specific to the current guild. |

## Utilities & Actions

| Tool Name | Module | Description |
|-----------|--------|-------------|
| `create_reminder` | `reminder.py` | Sets a timer or reminder for a specific user. |
| `calculate` | `math.py` | Performs mathematical calculations and expression evaluation. |
| `generate_image` | `image.py` | Generates images based on text prompts using AI providers. |
| `bot_info` | `bot_info.py` | Returns technical specs, version info, and bot status. |

## Discovery

| Tool Name | Module | Description |
|-----------|--------|-------------|
| `list_tools` | `tools_overview.py` | Dynamically lists all currently loaded tools and their signatures. |

## Tool Constraints

- **Character Limits**: Tool outputs are typically truncated to 1000-2000 characters to prevent prompt overflow.
- **Permission Awareness**: Certain tools (like admin-only actions) are filtered out by the `ToolsFactory` if the user lacks the required Discord permissions.
- **Safe Execution**: All tools are executed within an async environment with centralized error reporting via `func.report_error`.

---
*The LLM "Info Agent" typically uses these tools to gather context before the "Message Agent" formulates the final reply.*
