# File: `cogs/memory/db/stats_storage.py`

## Overview
StatsStorage: handles user statistics and log migration state persistence. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `StatsStorage`
Handles user_stats and log_migration_state table operations.

- **Attributes**:
  - `db` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(db: DatabaseConnection) -> None`: Initialize with a DatabaseConnection instance.
  - `get_user_stats(user_id: str, guild_id: str) -> Optional[Dict[Tuple[str, Any]]]`: Retrieve cumulative stats for a user in a guild.
  - `upsert_user_stats(user_id: str, guild_id: str, message_content: str, channel_name: str, timestamp: str) -> None`: Insert or update cumulative stats for a single message event.
  - `bulk_upsert_user_stats(records: List[Dict[Tuple[str, Any]]]) -> None`: Insert or update cumulative stats for a batch of message events.
  - `get_migration_state(guild_id: str) -> Optional[str]`: Get the last processed date for historical log migration.
  - `set_migration_state(guild_id: str, date_str: str) -> None`: Record the last processed date for historical log migration.
