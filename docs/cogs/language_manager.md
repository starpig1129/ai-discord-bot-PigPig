# Language Manager Cog Documentation

## Overview

The Language Manager cog is the backbone of the bot's multi-language localization system. It manages server-specific language preferences, loads translation data from a structured file system, and provides a centralized API for translating UI elements, command responses, and system messages.

## Features

- **Multi-language Support**: Supports English (en_US), Traditional Chinese (zh_TW), Simplified Chinese (zh_CN), and Japanese (ja_JP).
- **Server-specific Settings**: Each Discord server can independently set its preferred language.
- **Hierarchical Translation System**: Organizes translations into a nested directory structure (e.g., `translations/en_US/commands/botinfo.json`) for better maintainability.
- **LRU Caching**: Uses a multi-layer Least Recently Used (LRU) cache to speed up translation lookups and reduce disk I/O.
- **Dynamic Formatting**: Supports runtime variable injection into translation strings (e.g., `Hello {user}`).
- **Robust Error Handling**: Automatically reports missing translation keys through the centralized logging system while providing graceful fallbacks.

## Commands

### `/set_language`
Sets the display language for the current server.

**Parameters**:
- `language` (Choice): Select from the supported languages (繁體中文, 简体中文, English, 日本語).

**Requirements**: User must have Administrator permissions.

**Behavior**:
1. Saves the preference to `data/serverconfig/[GUILD_ID].json`.
2. Invalidates the system prompt cache to ensure the bot's persona adapts to the new language immediately.

### `/current_language`
Displays the language currently configured for the server.

## Technical Implementation

### Data Structure
Translations are stored in `Dict[str, Dict[str, Any]]`:
`lang_code -> category -> module -> sub_keys -> translation_string`

### Key Components

#### 1. `TranslationCache`
A custom class that manages up to 1000 translation entries. It tracks access times and frequency to perform LRU eviction when full.

#### 2. `_load_translations`
Recursively traverses the `translations/` directory at startup. It maps the directory structure to the internal dictionary, using file names as top-level keys within the language code.

#### 3. `translate()`
The main API for other cogs:
```python
translate(guild_id, "commands", "botinfo", "fields", "rating", user="PigPig")
```
- Retrieves server language.
- Generates a unique cache key based on the key path and formatting arguments.
- Traverses the internal dictionary.
- Formats the result string with provided `kwargs`.

### Cache Invalidation
When `/set_language` is called, the cog attempts to find the `PromptManager` and clear its `system_prompt` cache. This ensures that the AI's internal reasoning and personality switch to the new language instantly.

## Directory Structure
```
translations/
├── en_US/
│   ├── commands/
│   │   └── botinfo.json
│   └── system/
│       └── common.json
├── zh_TW/
└── ...
```

## Related Files
- `cogs/language_manager.py`: Core logic.
- `translations/`: Root directory for all localized content.
- `data/serverconfig/`: Storage for server-specific language settings.