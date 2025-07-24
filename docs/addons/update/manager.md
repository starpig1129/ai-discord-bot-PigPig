# Manager Module

**File:** [`addons/update/manager.py`](addons/update/manager.py)

This is the core module of the update system. The `UpdateManager` class orchestrates the entire update process, integrating all other components of the system, such as the version checker, downloader, and notifier.

## `UpdateManager` Class

This class provides a unified interface for managing the full update lifecycle.

### `__init__(self, bot)`

Initializes the `UpdateManager` and all its components.

*   **Parameters:**
    *   `bot`: The instance of the Discord bot.

### Methods

#### `async check_for_updates(self) -> Dict[str, Any]`

Checks for available updates.

*   **Returns:** A dictionary containing version information. See [`VersionChecker.check_for_updates()`](./checker.md#async-check_for_updates-self---dictstr-any) for details.

#### `async execute_update(self, interaction=None, force: bool = False) -> Dict[str, Any]`

Executes the full update process. This is a comprehensive workflow that includes:
1.  Checking for updates.
2.  Creating a backup (if enabled).
3.  Downloading the new version.
4.  Installing the update.
5.  Cleaning up old backups and downloaded files.
6.  Notifying the owner of the result.
7.  Initiating a graceful restart.

*   **Parameters:**
    *   `interaction` (Optional): The Discord interaction object that triggered the update.
    *   `force` (bool): If `True`, the update will be attempted even if no new version is detected.
*   **Returns:** A dictionary containing the results of the update, including a `success` flag and other relevant details.

#### `get_status(self) -> Dict[str, Any]`

Gets the current status of the update system.

*   **Returns:** A dictionary with status information, such as `status`, `progress`, `operation`, and `current_version`.

#### `async post_restart_initialization(self)`

Performs necessary checks and initializations after the bot has restarted. This is typically called once upon bot startup.

## `UpdateStatusTracker` Class

This class tracks the real-time status of the update process.

### Properties

*   `current_status` (str): The current status (e.g., "idle", "checking", "downloading", "error").
*   `progress` (int): The progress percentage of the current operation.
*   `current_operation` (str): A description of the current operation.
*   `error_message` (Optional[str]): An error message if the process has failed.

## `UpdateLogger` Class

This class logs all update events to a file for auditing and debugging purposes.

### `__init__(self, log_dir: str = "data/update_logs")`

Initializes the logger.

*   **Parameters:**
    *   `log_dir` (str): The directory where update logs are stored.