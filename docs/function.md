# Utility Singleton (function.py)

## Overview

The `function.py` module provides a global utility singleton (`func`) and error management tools used throughout the entire bot ecosystem.

## Core Components

### `Function` Class
The main utility class, exposed as the `func` singleton.
- **`set_bot(bot)`**: Links the Discord bot instance to the utility system.
- **`report_error(error, details)`**: The centralized error reporting engine.
- **`open_json(path)` / `update_json(path, data)`**: Safe JSON file I/O utilities.

### `ErrorDeduplicator`
Prevents the bot from spamming error reports to Discord.
- **Deduplication Logic**: Hashes error types, messages, and details.
- **Cooldown**: Suppresses identical reports for a configurable period (default: 12 hours).
- **Quota Awareness**: Detects API quota/rate-limit errors and logs them as Warnings rather than Errors.

## Error Reporting System

When `func.report_error` is called, the system:
1. Validates if the error is a duplicate via `ErrorDeduplicator`.
2. Categorizes the error (Quota vs. General Error).
3. Generates a rich Discord Embed containing:
    - **Title**: Error Report or Quota Warning.
    - **Error Details**: Truncated error message.
    - **Traceback**: Python stack trace formatted as a code block.
    - **Metadata**: Context details and UTC timestamp.
4. Sends the report to the configured bug report channel.

## Constants & Paths

- **`ROOT_DIR`**: The absolute path to the bot's root directory, used for reliable file access across different deployment environments.

---
*This module ensures system stability by providing robust error handling and prevents administrative fatigue by deduplicating redundant alerts.*
