# File: `cogs/memory/interfaces/storage_interface.py`

## Overview
Core logic and functionalities for storage_interface.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `ProceduralStorageInterface`
Interface for procedural (user) storage operations.

- **Methods**:
  - `get_user_info(discord_id: str) -> Optional[UserInfo]`: Executes get_user_info operation.
  - `delete_user_data(discord_id: str) -> bool`: Executes delete_user_data operation.
  - `update_user_data(discord_id: str, discord_name: str, procedural_memory: Optional[str], user_background: Optional[str], display_names: Optional[List[str]]) -> bool`: Executes update_user_data operation.
  - `update_user_activity(discord_id: str, discord_name: str) -> bool`: Executes update_user_activity operation.
  - `get_config(key: str) -> Optional[str]`: Executes get_config operation.
  - `set_config(key: str, value: str) -> None`: Executes set_config operation.

### `EpisodicStorageInterface`
Interface for episodic (channel memory state) storage operations.

- **Methods**:
  - `initialize_channel_memory_state() -> None`: Initialize the channel_memory_state table in the database.
  - `get_channel_memory_state(channel_id: int) -> Optional[Dict[Tuple[str, int]]]`: Get the memory state for a specific channel.
  - `update_channel_memory_state(channel_id: int, message_count: int, start_message_id: int, last_summary_timestamp: Optional[float], last_summary_text: Optional[str]) -> None`: Update the memory state for a specific channel.

### `StorageInterface`
Combined interface kept for backward compatibility.
