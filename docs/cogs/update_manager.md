# Update Manager Cog

**File:** [`cogs/update_manager.py`](cogs/update_manager.py)

This cog provides the Discord command interface for the bot's auto-update system. It allows administrators and the bot owner to check for, initiate, and monitor updates directly from Discord.

## Dependencies

This cog is the primary user interface for the **[Update System](../addons/update/index.md)** located in the `addons/` directory. It creates an instance of the `UpdateManager` class from that system to perform all the core logic.

## Commands

### `/update_check`

Checks if a new version of the bot is available on GitHub.

*   **Permissions:** Server Administrator
*   **Returns:** An embed showing the current and latest versions. If an update is available and the user is the bot owner, it will also display buttons to initiate the update.

### `/update_now`

Initiates the update process.

*   **Parameters:**
    *   `force` (Optional[bool]): If `True`, it will attempt to update even if no new version is detected.
*   **Permissions:** Bot Owner Only
*   **Behavior:** This command will trigger a confirmation prompt. Once confirmed, the `UpdateManager` begins the full update cycle, which includes backing up files, downloading the new version, installing it, and restarting the bot. Progress is sent to the owner via DMs.

### `/update_status`

Displays the current status of the update system.

*   **Permissions:** Server Administrator
*   **Returns:** An embed indicating the system's current state, such as "idle", "checking", "downloading", "error", etc.

### `/update_config`

(Work in Progress) Opens a menu for the bot owner to configure the auto-update settings.

*   **Permissions:** Bot Owner Only

## UI Components

The cog uses several `discord.ui.View` classes to create interactive components for the commands:

*   **`UpdateActionView`:** Shown after a successful `/update_check`, providing "Update Now" and "Remind Later" buttons.
*   **`UpdateConfirmView`:** A confirmation dialog with "Confirm Update" and "Cancel" buttons, shown before the update process begins.
*   **`UpdateConfigView`:** (Work in Progress) A view with buttons to toggle auto-update settings.