# File: `cogs/memory/db/procedural_storage.py`

## Overview
ProceduralStorage: handles users table and configuration storage. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `ProceduralStorage`
Handles users table and config storage.

- **Attributes**:
  - `db` (`Any`): Instance attribute.
  - `_user_cache` (`Dict[Tuple[str, UserInfo]]`): Instance attribute.
  - `_cache_size_limit` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(db: DatabaseConnection) -> None`: Executes __init__ operation.
  - `get_user_info(discord_id: str) -> Optional[UserInfo]`: Executes get_user_info operation.
  - `update_user_data(discord_id: str, discord_name: str, procedural_memory: Optional[str], user_background: Optional[str], display_names: Optional[List[str]]) -> bool`: Executes update_user_data operation.
  - `delete_user_data(discord_id: str) -> bool`: Executes delete_user_data operation.
  - `update_user_activity(discord_id: str, discord_name: str) -> bool`: Executes update_user_activity operation.
  - `get_config(key: str) -> Optional[str]`: Executes get_config operation.
  - `set_config(key: str, value: str) -> None`: Executes set_config operation.
  - `_update_cache(user_id: str, user_info: UserInfo) -> None`: Executes _update_cache operation.
