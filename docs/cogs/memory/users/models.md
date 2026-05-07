# File: `cogs/memory/users/models.py`

## Overview
UserInfo model for user data. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `UserInfo`
Dataclass matching the new `users` schema.

- **Attributes**:
  - `discord_id` (`str`): Class attribute.
  - `discord_name` (`str`): Class attribute.
  - `display_names` (`List[str]`): Class attribute.
  - `procedural_memory` (`Optional[str]`): Class attribute.
  - `user_background` (`Optional[str]`): Class attribute.
  - `created_at` (`Optional[datetime]`): Class attribute.

- **Methods**:
  - `to_dict() -> Dict[Tuple[str, Any]]`: Convert to dict for serialization; datetimes become ISO strings.
  - `from_dict(data: Dict[Tuple[str, Any]]) -> UserInfo`: Instantiate from dict, handling created_at and display_names formats.
