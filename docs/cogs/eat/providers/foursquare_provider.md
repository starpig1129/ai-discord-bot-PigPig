# File: `cogs/eat/providers/foursquare_provider.py`

## Overview
Foursquare Places API v3 Provider This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `FoursquareProvider`
Foursquare Places API 非同步 Provider。

- **Attributes**:
  - `api_key` (`Any`): Instance attribute.
  - `_session` (`Optional[aiohttp.ClientSession]`): Instance attribute.

- **Methods**:
  - `__init__(api_key: str) -> Any`: Executes __init__ operation.
  - `_get_session() -> aiohttp.ClientSession`: Executes _get_session operation.
  - `close() -> Any`: 關閉 aiohttp session，應在 cog_unload 中呼叫。
  - `search(keyword: str, lang: str) -> list[dict]`: 搜尋餐廳，返回最多 10 筆 PlaceResult 字典列表。
  - `_text_search(keyword: str) -> list[dict]`: 呼叫 Foursquare Place Search API。
  - `_get_first_photo(fsq_id: str) -> str`: 取得餐廳第一張照片 URL。
  - `_to_place_result(place: dict, photo_url: str) -> dict`: 將 Foursquare API 回應轉換為 PlaceResult 格式字典。
