# Core Bot Class (bot.py)

## Overview

The `PigPig` class is the central orchestrator of the Discord bot. It extends `commands.Bot` and integrates various subsystems like memory, music management, and AI-driven message processing.

## Subsystem Integration

The bot initializes several critical components in its `__init__` and `setup_hook` methods:

| Subsystem | Component | Description |
|-----------|-----------|-------------|
| **Logging** | `addons.logging` | Unified logging system with stdlib interception. |
| **Music** | `StateManager`, `UIManager` | Handles playback state and interactive UI components. |
| **Memory** | `ProceduralStorage`, `EpisodicStorage` | Persistent storage for user data and conversation context. |
| **LLM** | `Orchestrator` | Coordinates AI agents and tool execution. |
| **Updates** | `update.py` | Handles automatic version checking and installation. |

## Event Handlers

### `on_message`
The primary entry point for message interaction.
1. Logs message details to guild-specific loggers.
2. Tracks messages for episodic memory.
3. Processes traditional commands.
4. Delegates to `Orchestrator` for AI responses if:
    - The bot is mentioned.
    - Auto-response is enabled for the channel.
    - The message is a reply to the bot.

### `on_message_edit`
Handles message edits by deleting previous AI replies and generating new ones, ensuring the conversation stays consistent with the user's updated intent.

### `on_ready`
Triggers when the bot connects to Discord.
- Synchronizes command trees.
- Initializes per-guild loggers.
- Starts the periodic status update task.
- Generates `guilds_map.json` and `guilds_and_channels.json` for system monitoring.

## Lifecycle Management

- **`setup_hook`**: Dynamically loads all cogs from the `cogs/` directory and initializes core services.
- **`close`**: Performs a graceful shutdown by cancelling pending tasks and closing database connections.

## Key Methods

### `get_logger_for_guild(guild_id)`
Retrieves or creates a structured logger for a specific server, ensuring separate log streams for each guild.

### `change_status_task`
A background loop that rotates the bot's Discord status (e.g., "Listening to your voice", "Playing in N servers").

---
*The `PigPig` class follows a modular design, allowing components to be enabled or disabled via `addons/settings.py` without breaking core functionality.*
