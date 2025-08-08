# System Prompt System

**Location:** [`cogs/system_prompt/`](cogs/system_prompt/)

The System Prompt System is a highly flexible and powerful feature that allows for deep customization of the bot's core personality and behavior on a per-server or even per-channel basis. It is the primary mechanism for defining how the AI should respond in different contexts.

## Core Components

The system is a collection of specialized modules that work together:

*   **[System Prompt Manager](./manager.md):** The core engine that handles the three-tiered inheritance logic, configuration, and caching.
*   **[Commands](./commands.md):** Provides the unified `/system_prompt` slash command interface for users.
*   **[Permissions](./permissions.md):** Manages the detailed permission model for who can view and edit prompts.
*   **[Validators](./validators.md):** Includes data and cache validators to ensure content safety and data integrity.

## Three-Tiered Inheritance Model

The power of this system lies in its three-layered approach to building the final, effective system prompt:

1.  **Tier 1: Base YAML Prompt:** The foundation is a set of default prompts defined in YAML files within the `prompts/` directory. This provides a baseline personality for the bot.
2.  **Tier 2: Server-Level Override:** A server administrator can set a server-wide default prompt. This prompt overrides the base YAML prompt. It can either replace the base prompt entirely or append to it. It can also override specific modules from the YAML files.
3.  **Tier 3: Channel-Level Override:** A channel manager can set a prompt for a specific channel. This channel-specific prompt overrides both the server-level and base YAML prompts, providing the highest level of specificity.

When the bot generates a response, the **[Manager](./manager.md)** calculates the effective prompt by starting with the base, applying the server overrides, and finally applying the channel overrides. The result is then cached to ensure high performance.