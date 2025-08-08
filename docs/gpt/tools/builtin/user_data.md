# Built-in Tools - User Data

**File:** [`gpt/tools/builtin/user_data.py`](gpt/tools/builtin/user_data.py)

This module defines the `manage_user_data` tool, which provides the AI with a powerful way to remember and recall information about specific users.

## `@tool` `async def manage_user_data(...)`

This function allows the AI to read or save key-value data associated with a user's Discord ID.

*   **Parameters:**
    *   `context` (ToolExecutionContext): The standard execution context.
    *   `action` (str): The operation to perform. Must be either `'read'` or `'save'`.
    *   `user_id` (int): The Discord user ID to manage data for.
    *   `user_data` (Optional[str]): The data to save. This is required when the `action` is `'save'`.
*   **Logic:**
    1.  It retrieves the `UserDataCog` instance from the bot.
    2.  If the action is `'read'`, it calls the `_read_user_data` method on the cog.
    3.  If the action is `'save'`, it calls the `_save_user_data` method on the cog. This method contains the AI-powered logic for intelligently merging the new data with any existing data for that user.
*   **Returns:** A string confirming the result of the operation (e.g., "Data for user <@...> updated: ...").