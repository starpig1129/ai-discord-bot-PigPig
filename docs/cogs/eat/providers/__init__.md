# File: `cogs/eat/providers/__init__.py`

## Overview
餐廳搜尋 Provider 工廠 This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `_SeleniumFallbackProvider`
將 GoogleMapCrawler 包裝為符合 Provider 介面的 fallback。

- **Attributes**:
  - `_crawler` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(crawler: Any) -> Any`: Executes __init__ operation.
  - `async_search_list(keyword: str, lang: str) -> list[dict]`: Executes async_search_list operation.
  - `async_fetch_detail(url: str, lang: str) -> dict`: Executes async_fetch_detail operation.
  - `search(keyword: str, lang: str) -> list[dict]`: Executes search operation.
  - `close() -> Any`: Executes close operation.

## Functions

### `get_restaurant_provider() -> Any`
返回最合適的餐廳搜尋 Provider 實例。 Plays a key role in the system logic.
