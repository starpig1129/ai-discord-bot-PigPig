# Language Manager Cog

**File:** [`cogs/language_manager.py`](cogs/language_manager.py)

The `LanguageManager` cog is the central hub for all multi-language functionality in the bot. It allows servers to set their preferred language for bot responses and commands.

## Features

*   **Multi-language Support:** Loads translation files for various languages from the `translations/` directory.
*   **Server-specific Configuration:** Each server can set its own language preference, which is stored in `data/serverconfig/`.
*   **Centralized Translation:** Provides a single `translate` method that other cogs can use to get localized strings.
*   **Dynamic Command Localization:** Can be used to dynamically change the name and description of slash commands based on the server's language setting.

## Commands

### `/set_language`

Sets the display language for the bot on the current server.

*   **Parameters:**
    *   `language` (Choice): The language to set. The available options are dynamically loaded from the supported languages.
*   **Permissions:** Administrator

### `/current_language`

Displays the language currently being used by the bot on the server.

## Core Methods

### `translate(self, guild_id, *args, **kwargs) -> str`

This is the most important method in the cog. It retrieves a translated string based on the server's language setting.

*   **Parameters:**
    *   `guild_id` (str): The ID of the server to get the translation for.
    *   `*args`: A series of keys to navigate the nested JSON translation files (e.g., `"commands"`, `"play"`, `"responses"`, `"now_playing"`).
    *   `**kwargs`: Placeholder values to be formatted into the final string (e.g., `song_title="My Song"`).
*   **Returns:** The localized and formatted string.

### `get_server_lang(self, guild_id: str) -> str`

Retrieves the configured language for a specific server.

*   **Returns:** The language code (e.g., `"en_US"`, `"zh_TW"`).

### `get_instance(bot: commands.Bot) -> Optional['LanguageManager']`

A static method that allows other cogs to easily get a reference to the `LanguageManager` instance.

### Example Usage (from another cog)

```python
from .language_manager import LanguageManager

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager = LanguageManager.get_instance(self.bot)

    @app_commands.command(name="hello")
    async def hello_command(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        
        # Get a translated string
        greeting = self.lang_manager.translate(guild_id, "mycog", "greetings", "hello", user=interaction.user.mention)
        
        await interaction.response.send_message(greeting)