# Restart Module

**File:** [`addons/update/restart.py`](addons/update/restart.py)

This module provides a simple and reliable mechanism for restarting the bot, which is crucial after an update. It is designed to be robust, using system-level commands to ensure the restart process completes successfully.

## `SimpleRestartManager` Class

This class (also aliased as `GracefulRestartManager`) manages the entire restart process.

### `__init__(self, bot, restart_config: Optional[Dict[str, Any]] = None)`

Initializes the restart manager.

*   **Parameters:**
    *   `bot`: The instance of the Discord bot.
    *   `restart_config` (Optional[Dict[str, Any]]): A dictionary containing restart configuration, such as the path for the restart flag file and delay settings.

### Methods

#### `async execute_restart(self, reason: str = "update_restart") -> None`

Executes the restart process. This involves saving a restart flag, shutting down the bot gracefully, and then executing a system-specific command to start the bot again.

*   **Parameters:**
    *   `reason` (str): The reason for the restart, which is logged.

#### `async post_restart_check(self) -> bool`

Performs a check after the bot has restarted. It looks for the restart flag file to confirm that the restart was intentional and then runs a simple health check.

*   **Returns:** `True` if the check passes or if it was a normal startup, `False` if the health check fails.

#### `is_restart_pending(self) -> bool`

Checks if a restart is pending by looking for the existence of the restart flag file.

*   **Returns:** `True` if a restart is pending, `False` otherwise.

#### `cancel_restart(self) -> bool`

Cancels a pending restart by deleting the restart flag file.

*   **Returns:** `True` if the restart was successfully canceled, `False` otherwise.

### Example Usage

```python
# This class is typically used internally by the UpdateManager.
# The following is a conceptual example.

import asyncio
from addons.update.restart import SimpleRestartManager

# Assuming 'bot' is your discord.Client instance
# bot = discord.Client() 

async def perform_restart(bot_instance):
    restart_manager = SimpleRestartManager(bot_instance)
    
    print("Initiating restart...")
    await restart_manager.execute_restart(reason="manual_restart")
    print("This line will likely not be reached as the process exits.")

# To run this, you would need a running bot instance.
# asyncio.run(perform_restart(bot))