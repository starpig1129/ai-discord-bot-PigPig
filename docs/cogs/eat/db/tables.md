# File: `cogs/eat/db/tables.py`

## Overview
Core logic and functionalities for tables.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `UserPref`
Represents UserPref.

### `SearchRecord`
Represents SearchRecord.

- **Attributes**:
  - `discord_id` (`Any`): Instance attribute.
  - `keyword` (`Any`): Instance attribute.
  - `title` (`Any`): Instance attribute.
  - `tag` (`Any`): Instance attribute.
  - `address` (`Any`): Instance attribute.
  - `map_rate` (`Any`): Instance attribute.
  - `self_rate` (`Any`): Instance attribute.
  - `date` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(discord_id: str, title: str, keyword: str, tag: str, address: str, map_rate: str, self_rate: float) -> Any`: Executes __init__ operation.

### `Keywords`
Represents Keywords.

- **Attributes**:
  - `keyword` (`Any`): Instance attribute.
  - `add_date` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(keyword: String) -> Any`: Executes __init__ operation.
