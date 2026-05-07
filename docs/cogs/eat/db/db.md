# File: `cogs/eat/db/db.py`

## Overview
Core logic and functionalities for db.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `DB`
Represents DB.

- **Attributes**:
  - `engine` (`Any`): Instance attribute.

- **Methods**:
  - `__init__() -> None`: Executes __init__ operation.
  - `getKeywords() -> list`: Executes getKeywords operation.
  - `checkKeyword(keyword: String) -> Any`: Executes checkKeyword operation.
  - `storeKeyword(keyword: str) -> None`: Executes storeKeyword operation.
  - `storeSearchRecord(discord_id: str, title: str, keyword: str, map_rate: str, tag: str, map_address: str) -> int`: Executes storeSearchRecord operation.
  - `getSearchRecoreds(discord_id: str) -> list`: Executes getSearchRecoreds operation.
  - `updateRecordRate(id: int, new_rate: float) -> bool`: Executes updateRecordRate operation.
  - `getRecentRecords(discord_id: str, days: int) -> list`: 取得最近 N 天內的搜尋記錄，用於避免重複推薦
  - `getLikedRecords(discord_id: str) -> list`: 取得 self_rate >= 1 的記錄（用戶喜歡的）
  - `getDislikedRecords(discord_id: str) -> list`: 取得 self_rate <= -1 的記錄（用戶不喜歡的）
