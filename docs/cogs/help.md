# Help Cog

**File:** [`cogs/help.py`](cogs/help.py)

This cog provides a dynamic and localized help command that automatically lists all available application commands.

## Features

*   **Dynamic Command Discovery:** Automatically scans all registered cogs and their application commands.
*   **Localization:** Integrates with the `LanguageManager` to display command and cog descriptions in the server's configured language.
*   **Organized Display:** Groups commands by their respective cogs for a clear and organized presentation.

## Main Command

### `/help`

Displays a comprehensive list of all available slash commands, grouped by category (cog).

*   **Usage:**
    *   Simply run `/help` to see an embed containing all commands the user can access.

## Core Logic

The `help_command` method iterates through `self.bot.cogs`. For each cog, it retrieves the list of its application commands. It then uses the `LanguageManager` to fetch the localized names and descriptions for both the cog itself and each command within it.

If a translation is not available for a specific item, it gracefully falls back to the command's default description as defined in the source code, or a generic "No description" message. This ensures that the help command is always functional, even if translations are incomplete.