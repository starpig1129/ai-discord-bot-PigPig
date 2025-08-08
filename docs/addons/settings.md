# Settings Module

**File:** [`addons/settings.py`](addons/settings.py)

This module is responsible for managing all bot configurations. It loads settings from `settings.json` and environment variables from `.env`, providing a centralized point of access for all configuration values.

## `Settings` Class

The `Settings` class loads general bot settings from the `settings.json` file.

### `__init__(self, settings_path: str = "settings.json")`

Initializes the `Settings` object by loading configurations from the specified JSON file.

*   **Parameters:**
    *   `settings_path` (str): The path to the settings JSON file. Defaults to `"settings.json"`.

### Properties

The `Settings` class exposes the following configuration properties:

*   `invite_link` (str): The Discord invitation link for the bot.
*   `bot_prefix` (str): The command prefix for the bot.
*   `activity` (dict): The bot's activity status configuration.
*   `ipc_server` (dict): Configuration for the IPC server.
*   `version` (str): The current version of the bot.
*   `mongodb_uri` (str): The connection URI for MongoDB.
*   `music_temp_base` (str): The base path for temporary music files.
*   `youtube_cookies_path` (str): The path to the YouTube cookies file.
*   `model_priority` (list): The priority order for language models.
*   `auto_update` (dict): Auto-update settings.
*   `notification` (dict): Notification settings.
*   `security` (dict): Security-related settings.
*   `restart` (dict): Bot restart settings.
*   `github` (dict): GitHub repository information.
*   `ffmpeg` (dict): FFmpeg configuration.
*   `memory_system` (dict): Memory system settings.

### Example Usage

```python
from addons.settings import Settings

# Load settings from the default path
settings = Settings()

# Access a configuration value
print(f"Bot prefix: {settings.bot_prefix}")
```

## `TOKENS` Class

The `TOKENS` class loads sensitive keys and tokens from the `.env` file.

### `__init__(self)`

Initializes the `TOKENS` object by loading environment variables.

### Properties

*   `token` (str): The Discord bot token.
*   `client_id` (str): The bot's client ID.
*   `client_secret_id` (str): The bot's client secret ID.
*   `sercet_key` (str): A secret key for the bot.
*   `bug_report_channel_id` (int): The ID of the bug report channel.
*   `anthropic_api_key` (str): The API key for Anthropic services.
*   `openai_api_key` (str): The API key for OpenAI services.
*   `gemini_api_key` (str): The API key for Gemini services.
*   `tenor_api_key` (str): The API key for Tenor services.
*   `bot_owner_id` (int): The Discord ID of the bot owner.

### Example Usage

```python
from addons.settings import TOKENS

# Load tokens
tokens = TOKENS()

# Access a token
print(f"Bot owner ID: {tokens.bot_owner_id}")
```

## `UpdateSettings` Class

The `UpdateSettings` class manages configurations specifically for the auto-update system.

### `__init__(self, settings_path: str = "settings.json")`

Initializes the `UpdateSettings` object.

*   **Parameters:**
    *   `settings_path` (str): The path to the main settings file. Defaults to `"settings.json"`.

### Methods

#### `update_config(self, section: str, key: str, value)`

Updates a configuration value in the specified section.

*   **Parameters:**
    *   `section` (str): The configuration section (e.g., `"auto_update"`).
    *   `key` (str): The configuration key.
    *   `value`: The new value.

#### `is_auto_update_enabled(self) -> bool`

Checks if the auto-update feature is enabled.

*   **Returns:** `True` if enabled, `False` otherwise.

#### `get_check_interval(self) -> int`

Gets the interval for checking for updates.

*   **Returns:** The check interval in seconds.

#### `requires_owner_confirmation(self) -> bool`

Checks if updates require confirmation from the bot owner.

*   **Returns:** `True` if confirmation is required, `False` otherwise.

### Example Usage

```python
from addons.settings import UpdateSettings

# Load update settings
update_settings = UpdateSettings()

# Check if auto-update is enabled
if update_settings.is_auto_update_enabled():
    print("Auto-update is enabled.")