# Prompting System (Legacy)

**Location:** [`gpt/prompting/`](gpt/prompting/)

This directory contains the legacy YAML-based system for managing the bot's base system prompt. While the more advanced, database-driven **[System Prompt System](../../cogs/system_prompt/index.md)** is now the primary method for prompt customization, this legacy system still serves as the foundational layer (Tier 1) in the inheritance model.

## `PromptManager` Class

**File:** [`manager.py`](gpt/prompting/manager.py)

The `PromptManager` is the main entry point for this system. It is implemented as a singleton, ensuring that the YAML configuration is only loaded and parsed once.

*   **`get_system_prompt(self, ...)`:** This is the primary method. It retrieves the fully constructed system prompt.
    *   It first checks its internal cache for a pre-built prompt.
    *   If not cached, it uses the `PromptBuilder` to compose the prompt from the YAML file based on the `default_modules` list.
    *   It applies dynamic variable replacements (e.g., `{bot_id}`) and language-specific text replacements.
    *   The final prompt is then stored in the cache.
*   **File Watching:** The manager uses a `FileWatcher` to monitor `systemPrompt.yaml` for changes. If the file is modified, it automatically reloads the configuration and clears the cache.

## `PromptBuilder` Class

**File:** [`builder.py`](gpt/prompting/builder.py)

This class is responsible for constructing the final prompt string from its constituent parts defined in the YAML file.

*   **`build_system_prompt(self, config, modules)`:** It takes the parsed YAML config and a list of module names. It then iterates through the modules in the order specified in `composition.module_order` and concatenates their content into a single string. It also adds formatted titles for each module (e.g., "1. Personality and Expression").

## `PromptLoader` Class

**File:** [`loader.py`](gpt/prompting/loader.py)

A simple utility class that handles the reading and parsing of the `systemPrompt.yaml` file.

## `PromptCache` Class

**File:** [`cache.py`](gpt/prompting/cache.py)

A simple in-memory cache with a Time-To-Live (TTL) to store the final constructed prompts, reducing the need for repeated file I/O and string formatting.