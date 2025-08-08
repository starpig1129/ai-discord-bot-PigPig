# Notifier Module

**File:** [`addons/update/notifier.py`](addons/update/notifier.py)

This module is responsible for sending notifications related to the update process via Discord. It primarily communicates with the bot owner through DMs.

## `DiscordNotifier` Class

This class handles the sending of various notifications.

### `__init__(self, bot)`

Initializes the notifier.

*   **Parameters:**
    *   `bot`: The instance of the Discord bot.

### Methods

#### `async notify_update_available(self, version_info: Dict[str, Any]) -> bool`

Sends a notification that a new version is available, including release notes and an option to start the update.

*   **Parameters:**
    *   `version_info` (Dict[str, Any]): A dictionary containing details about the new version.
*   **Returns:** `True` if the notification was sent successfully, `False` otherwise.

#### `async notify_update_progress(self, stage: str, progress: int, details: str = "") -> bool`

Sends a notification about the current progress of an ongoing update.

*   **Parameters:**
    *   `stage` (str): The current stage of the update (e.g., "downloading", "installing").
    *   `progress` (int): The progress percentage (0-100).
    *   `details` (str): Optional additional details about the current step.
*   **Returns:** `True` if the notification was sent successfully.

#### `async notify_update_complete(self, result: Dict[str, Any]) -> bool`

Sends a notification when the update process is complete, indicating success or failure.

*   **Parameters:**
    *   `result` (Dict[str, Any]): A dictionary containing the results of the update.
*   **Returns:** `True` if the notification was sent successfully.

#### `async notify_update_error(self, error: Exception, context: str = "") -> bool`

Sends a notification when an error occurs during the update process.

*   **Parameters:**
    *   `error` (Exception): The exception object that was raised.
    *   `context` (str): The context in which the error occurred.
*   **Returns:** `True` if the notification was sent successfully.

#### `async notify_restart_success(self, restart_info: Dict[str, Any]) -> bool`

Sends a notification after the bot has successfully restarted.

*   **Parameters:**
    *   `restart_info` (Dict[str, Any]): Information about the restart.
*   **Returns:** `True` if the notification was sent successfully.

## `QuickUpdateView` Class

This `discord.ui.View` provides buttons for the user to interact with an update notification.

### Buttons

*   **立即更新 (Update Now):** Starts the update process. Can only be used by the bot owner.
*   **稍後提醒 (Remind Later):** Dismisses the current notification, which will reappear at the next update check.
*   **忽略 (Ignore):** Ignores the current update notification.