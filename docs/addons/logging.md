# Logging Manager

## Overview

The `addons/logging.py` module provides a high-performance, structured logging system. It is designed for multi-guild environments, ensuring that logs are categorized by server ID and stored in a machine-readable NDJSON format while maintaining a beautiful, colorized console output.

## Architecture

The system uses a **Dual-Sink Architecture**:

1. **Console Sink (Loguru)**: Provides immediate, human-readable feedback in the terminal with customizable colors and emojis.
2. **File Sink (NDJSON)**: Writes structured logs to the `logs/` directory for long-term storage and analysis.

### `BackgroundWriter`
To prevent logging from blocking the bot's main execution loop, all file writes are handled by a dedicated background thread:
- **Batching**: Logs are collected into batches (default 500 records) or flushed every 2 seconds.
- **Grouping**: Logs are grouped by `server_id`, `date`, and `level` to minimize disk syscalls.
- **Emergency Stash**: If the primary log directory is unwritable, logs are diverted to an `emergency/` directory.

## Structured Logging

Instead of plain text strings, PigPig Bot uses structured `LogRecord` objects:
- `timestamp`: ISO 8601 UTC.
- `level`: DEBUG, INFO, WARNING, ERROR, CRITICAL.
- `source`: The module or component name.
- `server_id`: The Discord Guild ID.
- `user_id`: The ID of the user who triggered the event.
- `action`: A short slug identifying the operation (e.g., `cmd_executed`).
- `extra`: A dictionary for arbitrary metadata (e.g., LLM tokens, response times).

## Usage

The primary entry point is `get_logger()`:

```python
from addons.logging import get_logger

# Initialize logger for a specific server
logger = get_logger(server_id="123456789", source="my_module")

# Basic logging
logger.info("Something happened")

# Bind context (structlog-style)
bound_logger = logger.bind(user_id="alice", action="save_data")
bound_logger.error("Failed to save", extra={"error_code": 500})
```

## Features

- **ANSI Color Support**: Automatic detection of terminal color capabilities (Windows 10+ supported).
- **Emoji Indicators**: Optional visual icons for log levels (🔍, ✅, ⚠️, ❌, 🚨).
- **Intercept Handler**: Automatically redirects standard Python `logging` calls from third-party libraries (like `discord.py` or `sqlalchemy`) into the structured system.
- **Per-Level Retention**: Configurable log rotation and cleanup policies via `base.yaml`.

---
*The logging system is a critical tool for debugging LLM interactions and monitoring bot health across multiple servers.*