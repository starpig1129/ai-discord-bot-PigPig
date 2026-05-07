# File: `cogs/eat/providers/googlemap_crawler.py`

## Overview
Core logic and functionalities for googlemap_crawler.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `GoogleMapCrawler`
Represents GoogleMapCrawler.

- **Attributes**:
  - `_lock` (`Any`): Instance attribute.

- **Methods**:
  - `__init__() -> Any`: Executes __init__ operation.
  - `search_list(keyword: str, lang: str) -> list[dict]`: 快速爬取搜尋結果列表。
  - `fetch_detail(url: str, lang: str) -> dict`: 導航至特定餐廳頁面，抓取詳盡資訊（地址、評分、照片等）。
  - `async_search_list(keyword: str, lang: str) -> list[dict]`: Executes async_search_list operation.
  - `async_fetch_detail(url: str, lang: str) -> dict`: Executes async_fetch_detail operation.
  - `close() -> Any`: Executes close operation.
