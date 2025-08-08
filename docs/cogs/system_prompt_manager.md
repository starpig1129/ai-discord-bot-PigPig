# System Prompt Manager Cog

**File:** [`cogs/system_prompt_manager.py`](cogs/system_prompt_manager.py)

This cog serves as the central coordinator for the powerful System Prompt management feature. It acts as the main entry point, loading and integrating all the necessary components from the `cogs/system_prompt/` directory.

## Dependencies

This cog is the primary interface for the **[System Prompt System](./system_prompt/index.md)**. It initializes and provides access to the core components of this system, including:

*   **`SystemPromptManager`:** The core engine that handles the logic of storing, retrieving, and combining prompts.
*   **`SystemPromptCommands`:** The cog that contains all the user-facing slash commands for managing prompts.
*   **`PermissionValidator`:** The component responsible for checking if a user has the required permissions to manage prompts.

## Role as a Coordinator

The `SystemPromptManagerCog` itself does not contain any user-facing commands. Its main responsibilities are:

1.  **Initialization:** It creates instances of the `SystemPromptManager`, `PermissionValidator`, and `SystemPromptCommands` cog.
2.  **Cog Loading:** It ensures that the `SystemPromptCommands` cog is properly loaded into the bot, making the slash commands available to users.
3.  **Central Access Point:** It provides getter methods (`get_system_prompt_manager`, `get_permission_validator`) for other parts of the bot (like the core message handler) to easily access the system's functionality.
4.  **Convenience Methods:** It offers high-level methods like `get_effective_system_prompt` that simplify the process for external modules to get the final, combined system prompt for a specific channel.

## Owner-only Commands

This cog also includes two hidden commands for the bot owner to manage the module itself:

*   `/system_prompt_status`: Displays the status of the module, including cache size and loaded components.
*   `/system_prompt_clear_cache`: Allows the owner to clear the prompt cache for a specific server or for all servers.