# StatsCog: User Awareness & Statistics

## Overview

The `StatsCog` is a specialized module designed for real-time user interaction tracking and historical log migration. It provides the foundation for "User Awareness" by maintaining a database of user activity across all servers the bot participates in.

## Core Features

### 📊 Real-time Tracking
- Listens for every incoming message in allowed channels.
- Records user ID, guild ID, channel name, message content, and timestamps.
- Updates the `user_stats` table in the procedural database.
- Uses `asyncio.shield` to ensure database writes are not interrupted by message deletions or task cancellations.

### 📂 Historical Log Migration
- Automatically ingests historical NDJSON log files (`info.jsonl`) into the database.
- Runs as a low-priority background task on cog load.
- Tracks migration progress via the `log_migration_state` table to avoid redundant processing.
- **Performance Safeguards**:
    - Batch processing (commits every 500 records).
    - Event loop yielding (`asyncio.sleep(0)`) to maintain bot responsiveness.
    - Day-by-day throttling (30-second delay between processing different days).

## Database Schema

The cog interacts with two main tables:

### `user_stats`
| Column | Type | Description |
|--------|------|-------------|
| `user_id` | TEXT | Discord Snowflake ID of the user |
| `guild_id` | TEXT | Discord Snowflake ID of the server |
| `channel_name` | TEXT | Name of the channel where message was sent |
| `message_content` | TEXT | The content of the message |
| `timestamp` | TEXT | ISO 8601 timestamp of the message |

### `log_migration_state`
| Column | Type | Description |
|--------|------|-------------|
| `guild_id` | TEXT | The server being migrated |
| `last_date` | TEXT | The last YYYYMMDD directory successfully processed |

## Lifecycle Management

1. **Initialization**: Connects to the procedural database via the bot's `procedural_storage`.
2. **Cog Load**: Starts the `_migrate_logs_background` task.
3. **Cog Unload**: Safely cancels any ongoing migration tasks.

## Configuration

The cog relies on the `procedural_storage` being initialized on the bot instance. If the storage is missing, the cog will log a warning and disable tracking.

---
*This module is a key component of the PigPig Bot's cognitive architecture, enabling the bot to 'remember' who users are and how they interact over time.*
