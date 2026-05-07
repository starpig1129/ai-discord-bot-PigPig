# File: `cogs/memory/db/connection.py`

## Overview
Database connection manager for the memory cog. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `DatabaseConnection`
Manage SQLite connections per-thread and provide thread-safe access.

- **Attributes**:
  - `db_path` (`Any`): Instance attribute.
  - `bot` (`Any`): Instance attribute.
  - `_loop` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.
  - `_lock` (`Any`): Instance attribute.
  - `_connections` (`Dict[Tuple[int, sqlite3.Connection]]`): Instance attribute.

- **Methods**:
  - `__init__(db_path: Union[Tuple[str, Path]], bot: Optional[PigPig]) -> Any`: Initialize connection manager.
  - `_report_error_threadsafe(exc: Exception, ctx: str) -> None`: Report errors in a thread-safe manner to the async error reporter.
  - `get_connection() -> Any`: Context manager that yields a sqlite3.Connection bound to the current thread.
  - `close_connections() -> None`: Close all managed SQLite connections.
