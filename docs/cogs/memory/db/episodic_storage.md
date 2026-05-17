# File: `cogs/memory/db/episodic_storage.py`

## Overview
EpisodicStorage: handles message-related tables (messages, pending_messages, messages_archive). This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `EpisodicStorage`
Handles channel memory state management.

- **Attributes**:
  - `db` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(db: DatabaseConnection) -> None`: Executes __init__ operation.
  - `initialize_channel_memory_state() -> None`: Initialize the channel_memory_state table in the database.
  - `get_channel_memory_state(channel_id: int) -> Optional[Dict[Tuple[str, int]]]`: Get the memory state for a specific channel.
  - `update_channel_memory_state(channel_id: int, message_count: int, start_message_id: int, last_summary_timestamp: Optional[float], last_summary_text: Optional[str]) -> None`: Update the memory state for a specific channel.
