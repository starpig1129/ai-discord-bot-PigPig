# Entry Point (main.py)

## Overview

`main.py` is the execution entry point for the PigPig Discord Bot. It handles environment setup, bot instantiation, and the initial connection to Discord.

## Startup Workflow

1. **Environment Loading**: Uses `python-dotenv` to load secrets and configuration from `.env`.
2. **Intent Configuration**: Sets up Discord Intents (Message Content, Members, Presences) based on the `base_config`.
3. **Bot Instantiation**: Creates the `PigPig` bot object with custom `CommandTree` for guild-only command validation.
4. **Version Check**: Spawns a background thread to check for project updates without blocking the bot's connection.
5. **Execution**: Calls `bot.run()` using the token from `addons.tokens`.

## Custom Components

### `CommandCheck`
A custom `app_commands.CommandTree` that overrides `interaction_check` to ensure that all slash commands are executed within a server (guild) context, preventing errors in Direct Messages.

## Background Services

### Version Checker Thread
To ensure the bot is always up to date, a dedicated daemon thread runs `VersionChecker` at startup. It logs warnings if a newer version is available on GitHub and provides the update command.

## Error Handling & Shutdown

The entry point includes a `try...except...finally` block to handle:
- **KeyboardInterrupt**: Catches `Ctrl+C` for manual stops.
- **Graceful Shutdown**: Ensures `bot.close()` is called to clean up resources, close database connections, and cancel pending asyncio tasks.

---
*For daily operation, simply run `python main.py`. For update management, refer to the [Update Guide](update.md).*
