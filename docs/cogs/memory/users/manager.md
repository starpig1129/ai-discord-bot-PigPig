# File: `cogs/memory/users/manager.py`

## Overview
User manager depending on StorageInterface. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `SQLiteUserManager`
Lightweight user manager that delegates storage operations to StorageInterface.

- **Attributes**:
  - `storage` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.
  - `_user_cache` (`Dict[Tuple[str, UserInfo]]`): Instance attribute.
  - `_cache_size_limit` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(storage: StorageInterface) -> Any`: Initialize with a StorageInterface implementation.
  - `get_user_info(user_id: str, use_cache: bool) -> Optional[UserInfo]`: Retrieve user info via storage and update cache.
  - `get_multiple_users(user_ids: List[str], use_cache: bool) -> Dict[Tuple[str, UserInfo]]`: Retrieve multiple users, leveraging cache and storage concurrently.
  - `update_user_data(user_id: str, user_data: Any, display_name: Optional[str]) -> bool`: Extracts fields from user_data and delegates to storage.
  - `delete_user_data(user_id: str) -> bool`: Delegate deletion to storage and invalidate cache.
  - `update_user_activity(user_id: str, display_name: str) -> bool`: Delegate activity update to storage and invalidate cache.
  - `search_users_by_display_name(name_pattern: str, limit: int) -> List[UserInfo]`: Attempt to use storage search; fall back to simple cache scan if unavailable.
  - `get_user_statistics() -> Dict[Tuple[str, Any]]`: Return statistics; delegate to storage if available otherwise return cache-based stats.
  - `migrate_from_mongodb(mongodb_collection: Any) -> int`: Migrate users by delegating to update_user_data for each document.
  - `_update_cache(user_id: str, user_info: UserInfo) -> Any`: Update in-memory cache with eviction.
  - `clear_cache() -> Any`: Clear in-memory cache.
  - `cleanup_inactive_users(days: int) -> int`: Delegate cleanup if storage provides method; otherwise no-op.

## Functions

### `extract_participant_ids(message: Any, conversation_history: List[Any]) -> set`
Extract participant IDs from a message and recent conversation history. Plays a key role in the system logic.
