# System Prompt System - Manager

**File:** [`cogs/system_prompt/manager.py`](cogs/system_prompt/manager.py)

The `SystemPromptManager` is the core engine of the system prompt feature. It handles the complex logic of inheriting and combining prompts from different levels, manages caching, and ensures content is safe.

## `SystemPromptManager` Class

### `__init__(self, bot)`

Initializes the manager, creating instances of the `SystemPromptCache`, `PromptValidator`, and `PermissionValidator`. It also sets up the data directory for storing configuration files.

### `get_effective_prompt(self, channel_id, guild_id, ...)`

This is the most important method in the manager. It calculates the final system prompt to be used for a given channel by applying the three-tiered inheritance model.

*   **Process:**
    1.  **Cache Check:** It first checks the `SystemPromptCache` for a valid, non-expired entry for the channel. If found, it returns the cached prompt immediately.
    2.  **Tier 1 (Base):** It retrieves the base prompt from the YAML files using the `gpt.prompting.manager`.
    3.  **Tier 2 (Server):** It loads the server's configuration file (`{guild_id}.json`) and applies the `server_level` overrides to the base prompt using `_apply_server_overrides`.
    4.  **Tier 3 (Channel):** It then applies the channel-specific overrides from the configuration file using `_apply_channel_overrides`.
    5.  **Localization & Variables:** It applies language localizations and replaces dynamic variables (like `{current_time}`).
    6.  **Cache Update:** The final, combined prompt is stored in the cache for future use.
*   **Returns:** A dictionary containing the final `prompt` string and its `source` (e.g., 'cache', 'channel', 'server', 'yaml').

### Configuration Management

*   **`set_channel_prompt(...)` / `set_server_prompt(...)`:** These methods handle the saving of new or updated prompt configurations. They first validate the input using the `PromptValidator` and then write the data to the appropriate JSON configuration file.
*   **`remove_channel_prompt(...)` / `remove_server_prompt(...)`:** These methods remove the configuration for a channel or a server, causing them to fall back to the next level of the inheritance chain.
*   **`_load_guild_config(...)` / `_save_guild_config(...)`:** Private methods for reading from and writing to the per-server JSON files.

### Caching (`SystemPromptCache`)

The manager uses an in-memory `SystemPromptCache` with a Time-To-Live (TTL).
*   **`get(...)`:** Retrieves a prompt from the cache if it's not expired.
*   **`set(...)`:** Stores a newly generated prompt in the cache with a timestamp.
*   **`invalidate(...)`:** Clears the cache for a specific channel or an entire server. This is called automatically whenever a prompt is updated or removed to ensure changes take effect immediately.

### Validation (`PromptValidator`)

This internal class ensures the safety and integrity of user-provided prompts.
*   **`validate_prompt_content(...)`:** Checks if the prompt content exceeds the maximum length (`MAX_PROMPT_LENGTH`) and scans it for potentially malicious code patterns (like `<script>` tags or `javascript:` URIs) using a list of regular expressions.