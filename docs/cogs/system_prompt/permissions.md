# System Prompt System - Permissions

**File:** [`cogs/system_prompt/permissions.py`](cogs/system_prompt/permissions.py)

The `PermissionValidator` class is the dedicated security component for the system prompt feature. It provides a centralized place to check if a user has the authority to perform specific actions, such as viewing, editing, or removing prompts.

## `PermissionValidator` Class

### `__init__(self, bot)`

Initializes the validator with a reference to the bot instance, which is needed to fetch user and guild information.

### Key Methods

#### `can_modify_channel_prompt(self, user, channel, ...)`

Checks if a user has permission to modify the system prompt for a specific channel.

*   **Permission Hierarchy (in order):**
    1.  **Bot Owner:** Always has permission.
    2.  **Server Administrator:** Users with the `Administrator` permission in the server.
    3.  **Channel Manager:** Users with the `Manage Channels` permission for that specific channel.
    4.  **Custom Permissions:** Checks the server's configuration file for any custom roles or users that have been granted permission.

#### `can_modify_server_prompt(self, user, guild, ...)`

Checks if a user has permission to modify the server-wide default system prompt.

*   **Permission Hierarchy:**
    1.  **Bot Owner:** Always has permission.
    2.  **Server Administrator:** Users with the `Administrator` permission.
    3.  **Custom Permissions:** Checks the server's configuration for roles that have been granted server-level prompt management permissions.

#### `can_view_prompt(self, user, channel, ...)`

Checks if a user can view a prompt. This permission is intentionally broad: any user who can view a channel is allowed to see the system prompt that applies to it.

#### `validate_permission_or_raise(self, user, action, ...)`

A crucial enforcement method used by the command handlers. It performs a permission check and, if the check fails, it raises a `PermissionError`. This simplifies the code in the command handlers, as they can wrap their logic in a `try...except` block.