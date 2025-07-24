# System Prompt System - Commands

**File:** [`cogs/system_prompt/commands.py`](cogs/system_prompt/commands.py)

The `SystemPromptCommands` cog provides the user-facing interface for the entire system prompt feature. It is designed around a single, unified slash command that uses Discord UI components for all interactions.

## `SystemPromptCommands` Class

### `__init__(self, bot)`

Initializes the command cog, creating instances of the `SystemPromptManager` and `PermissionValidator` to handle the backend logic and security.

### Main Command: `/system_prompt`

This is the sole entry point for users. Instead of having multiple commands for different actions, this command opens a main menu from which all other actions are launched.

*   **Behavior:** When executed, it creates and displays a `SystemPromptMainView` and a descriptive embed. All subsequent interactions happen through the buttons on this view. This approach simplifies the user experience and reduces the number of slash commands needed.

### UI-Driven Workflow

All functionality is handled through views and modals defined in `cogs/system_prompt/ui/`.

*   **`SystemPromptMainView`:** The main menu that appears when `/system_prompt` is run. It has buttons for:
    *   **Set Prompt:** Leads to a choice between setting the server or channel prompt, which then opens the `SystemPromptModal`.
    *   **View Config:** Shows the current effective prompt for the channel.
    *   **Edit Modules:** Opens a `ModuleSelectView` to allow editing specific YAML modules.
    *   **Copy Prompt:** Opens a `ChannelSelectView` to copy a prompt to another channel.
    *   **Remove Prompt:** Opens a confirmation view to delete a server or channel prompt.
*   **`SystemPromptModal`:** A popup form where users can type in the main prompt content and select modules to include.
*   **`ConfirmationView`:** A generic view with "Confirm" and "Cancel" buttons used for destructive actions like removing a prompt.

### Error Handling

The cog uses a decorator, `@handle_system_prompt_error`, on its main command. This wrapper catches all custom exceptions defined in `exceptions.py` (like `PermissionError`, `ValidationError`, `PromptNotFoundError`) and provides a consistent, user-friendly error message in an ephemeral response, preventing crashes and improving user feedback.