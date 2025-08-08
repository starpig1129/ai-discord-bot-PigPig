# Security Module

**File:** [`addons/update/security.py`](addons/update/security.py)

This module provides security features for the update process, including permission checking, file backups, and configuration protection.

## `UpdatePermissionChecker` Class

This class is used to verify if a user has the necessary permissions to perform update-related actions.

### `__init__(self)`

Initializes the permission checker by loading the bot owner's ID from the environment variables.

### Methods

#### `check_update_permission(self, user_id: int) -> bool`

Checks if a user has permission to execute an update. Only the bot owner is permitted.

*   **Parameters:**
    *   `user_id` (int): The Discord ID of the user.
*   **Returns:** `True` if the user is the bot owner, `False` otherwise.

#### `check_status_permission(self, interaction: discord.Interaction) -> bool`

Checks if a user has permission to view the update system's status. Permitted for server administrators and the bot owner.

*   **Parameters:**
    *   `interaction` (discord.Interaction): The interaction object from a command.
*   **Returns:** `True` if the user has permission, `False` otherwise.

## `BackupManager` Class

This class manages the creation, restoration, and cleanup of backups.

### `__init__(self, backup_dir: str = "data/backups")`

Initializes the backup manager.

*   **Parameters:**
    *   `backup_dir` (str): The directory where backups are stored. Defaults to `"data/backups"`.

### Methods

#### `create_backup(self, protected_files: Optional[List[str]] = None) -> str`

Creates a backup of the current bot state, including specified protected files and directories.

*   **Parameters:**
    *   `protected_files` (Optional[List[str]]): A list of files and directories to include in the backup.
*   **Returns:** The unique ID of the created backup.
*   **Raises:** `Exception` if the backup process fails.

#### `rollback_to_backup(self, backup_id: str) -> bool`

Restores the bot's files from a specified backup.

*   **Parameters:**
    *   `backup_id` (str): The ID of the backup to restore.
*   **Returns:** `True` if the rollback is successful, `False` otherwise.

#### `list_backups(self) -> List[dict]`

Lists all available backups.

*   **Returns:** A list of dictionaries, where each dictionary contains information about a backup.

#### `cleanup_old_backups(self, max_backups: int = 5) -> None`

Deletes the oldest backups, keeping a specified number of recent backups.

*   **Parameters:**
    *   `max_backups` (int): The maximum number of backups to retain.

## `ConfigProtector` Class

This class is dedicated to backing up and restoring critical configuration files during the update process.

### Methods

#### `backup_configs(self, backup_path: str) -> bool`

Backs up critical configuration files to a specified path.

*   **Parameters:**
    *   `backup_path` (str): The path where the configuration backup will be stored.
*   **Returns:** `True` if successful, `False` otherwise.

#### `restore_configs(self, backup_path: str) -> bool`

Restores configuration files from a backup.

*   **Parameters:**
    *   `backup_path` (str): The path of the configuration backup.
*   **Returns:** `True` if successful, `False` otherwise.

#### `verify_configs(self) -> bool`

Verifies the integrity of critical configuration files (e.g., checks if JSON files are valid).

*   **Returns:** `True` if all configurations are valid, `False` otherwise.