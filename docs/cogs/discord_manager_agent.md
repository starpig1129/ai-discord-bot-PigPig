# Discord Manager Agent Cog

**File:** [`cogs/discord_manager_agent.py`](cogs/discord_manager_agent.py)

This cog introduces a powerful "Discord Manager Agent" that allows server administrators to manage their server using natural language commands. It leverages a Large Language Model (LLM) to parse instructions and execute corresponding actions.

## Features

*   **Natural Language Processing:** Understands commands written in plain language (e.g., "create a text channel named 'general'").
*   **Multi-faceted Management:** Can manage channels, roles, voice channels, and categories.
*   **Security and Auditing:** Includes a security manager to validate permissions and an audit logger to record all actions performed by the agent.

## Main Command

### `/manage`

The primary command for interacting with the agent.

*   **Parameters:**
    *   `instruction` (str): The natural language instruction describing the action to be performed.
*   **Permissions:** Manage Server

### Example Usage

```
/manage instruction: create a text channel called #announcements and a role called "Member" with a green color
```

## Core Components

### `DiscordManagerAgent` Class

The main cog class that orchestrates the entire process. It receives the command, validates permissions, invokes the parser, executes the action, and logs the result.

### `InstructionParser` Class

This class is responsible for interpreting the user's natural language instruction.

*   **`parse(self, instruction: str)`:** This method sends the instruction to an LLM (configured via `gpt/discord_agent_prompt.txt`) which then returns a structured JSON object. This JSON object contains the `action`, `target_type`, and `additional_params` needed to execute the command.

### `SecurityManager` Class

This class handles security aspects of the agent.

*   **`validate_operation(self, member, operation)`:** Checks if the user has the required Discord permissions to perform the requested operation.
*   **`audit_log(self, operation, member, result)`:** Logs the details of every operation to `logs/agent_audit.log` for accountability and debugging.

## Supported Operations

The agent supports a variety of operations on different Discord entities:

*   **Channels:** `create`, `delete`, `modify`, `move`
*   **Roles:** `create`, `delete`, `modify`, `assign`
*   **Voice:** `move`, `disconnect`, `limit`
*   **Categories:** `create`, `delete`, `organize`
*   **Permissions:** `set`, `sync`, `audit`