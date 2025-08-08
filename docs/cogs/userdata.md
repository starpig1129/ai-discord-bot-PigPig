# User Data Cog

**File:** [`cogs/userdata.py`](cogs/userdata.py)

This cog provides a system for storing and managing data specific to individual users. It is designed to be used both directly by users via a slash command and programmatically by the bot's AI tools.

## Features

*   **Persistent Storage:** User data is stored in the database via the `UserManager`, ensuring it persists across bot restarts.
*   **AI-powered Merging:** When new data is saved for a user who already has existing data, an LLM is used to intelligently merge the old and new information, preventing duplicates and maintaining consistency.
*   **Dual Interface:**
    *   A `/userdata` slash command for manual data management.
    *   A `manage_user_data` method that can be called by other parts of the bot, particularly AI-driven tools.

## Main Command

### `/userdata`

Allows users to read or save their personal data.

*   **Parameters:**
    *   `action` (Choice): The action to perform.
        *   `讀取 (Read)`: Retrieves and displays the user's current data.
        *   `保存 (Save)`: Saves or updates the user's data.
    *   `user` (Optional[discord.User]): The user to target. Defaults to the command invoker.
    *   `user_data` (Optional[str]): The data to save. Required when `action` is `Save`.

## Core Logic

### `manage_user_data(...)`

This is the central dispatcher method. It checks for the availability of the `UserManager` and routes the request to the appropriate helper method (`_read_user_data` or `_save_user_data`) based on the `action`.

### `_read_user_data(...)`

This method retrieves the `user_data` field for a given user ID from the database via `self.user_manager.get_user_info()`.

### `_save_user_data(...)`

This method handles the logic for saving data.

1.  It first retrieves any existing data for the user.
2.  If existing data is found, it constructs a prompt for an LLM, providing both the old and new data. The LLM is instructed to merge them intelligently.
3.  If no existing data is found, it uses the new data directly.
4.  The final, merged data is then saved to the database using `self.user_manager.update_user_data()`.