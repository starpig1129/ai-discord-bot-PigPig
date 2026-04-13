"""Foursquare Places API v3 Provider

免費層：每月 1000 次 API 呼叫
API 文件：https://docs.foursquare.com/developer/reference/place-search
"""
import asyncio
import os
import urllib.parse
from typing import Optional
import aiohttp

from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="eat.foursquare")

# Foursquare 餐廳類別 ID（13000 = Food，包含所有子類別）
FOOD_CATEGORY_ID = "13000"
FSQ_API_BASE = "https://api.foursquare.com/v3"


class FoursquareProvider:
    """Foursquare Places API 非同步 Provider。

    使用 aiohttp 發送非阻塞 HTTP 請求，取得餐廳列表和詳細資訊。
    無 API key 時請改用 GoogleMapCrawler fallback。
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": self.api_key,
                    "Accept": "application/json",
                }
            )
        return self._session

    async def close(self):
        """關閉 aiohttp session，應在 cog_unload 中呼叫。"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def search(self, keyword: str, lang: str = "zh_TW") -> list[dict]:
        """搜尋餐廳，返回最多 10 筆 PlaceResult 字典列表。

        Args:
            keyword: 搜尋關鍵字（例如：「日本料理」、「牛肉麵」）

        Returns:
            list[dict]：PlaceResult 相容字典列表，失敗時返回空列表
        """
        try:
            raw_places = await self._text_search(keyword)
            if not raw_places:
                logger.warning(f"Foursquare 搜尋「{keyword}」無結果")
                return []

            # 並行取得前 5 筆的照片（詳細資訊已在 search 回應中包含）
            photo_tasks = [self._get_first_photo(p.get("fsq_id", "")) for p in raw_places[:5]]
            photos = await asyncio.gather(*photo_tasks, return_exceptions=True)

            results = []
            for i, place in enumerate(raw_places):
                photo_url = ""
                if i < len(photos) and isinstance(photos[i], str):
                    photo_url = photos[i]

                results.append(self._to_place_result(place, photo_url))

            logger.info(f"Foursquare 搜尋「{keyword}」取得 {len(results)} 筆結果")
            return results

        except Exception as e:
            from function import func
            await func.report_error(e, f"FoursquareProvider.search: {e}")
            return []

    async def _text_search(self, keyword: str) -> list[dict]:
        """呼叫 Foursquare Place Search API。"""
        session = self._get_session()
        params = {
            "query": f"{keyword}餐廳",
            "categories": FOOD_CATEGORY_ID,
            "limit": 10,
            "fields": "fsq_id,name,rating,categories,location,geocodes,hours,tel,price",
        }
        url = f"{FSQ_API_BASE}/places/search"
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"Foursquare API 錯誤 {resp.status}: {body[:200]}")
                    return []
                data = await resp.json()
                return data.get("results", [])
        except asyncio.TimeoutError:
            logger.warning("Foursquare API 請求逾時")
            return []

    async def _get_first_photo(self, fsq_id: str) -> str:
        """取得餐廳第一張照片 URL。

        Args:
            fsq_id: Foursquare 地點 ID

        Returns:
            照片 URL 字串，失敗時返回空字串
        """
        if not fsq_id:
            return ""
        session = self._get_session()
        url = f"{FSQ_API_BASE}/places/{fsq_id}/photos"
        params = {"limit": 1}
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return ""
                photos = await resp.json()
                if not photos:
                    return ""
                photo = photos[0]
                prefix = photo.get("prefix", "")
                suffix = photo.get("suffix", "")
                if prefix and suffix:
                    return f"{prefix}400x300{suffix}"
                return ""
        except Exception:
            return ""

    def _to_place_result(self, place: dict, photo_url: str = "") -> dict:
        """將 Foursquare API 回應轉換為 PlaceResult 格式字典。"""
        # 地址
        location = place.get("location", {})
        address_parts = [
            location.get("address", ""),
            location.get("locality", ""),
        ]
        address = " ".join(p for p in address_parts if p) or "地址未提供"

        # 類別
        categories = place.get("categories", [])
        category = categories[0].get("name", "餐廳") if categories else "餐廳"

        # 評分（Foursquare 為 0-10，轉換為 0-5）
        raw_rating = place.get("rating", 0)
        rating = round(raw_rating / 2, 1) if raw_rating else 0.0

        # 價格等級（Foursquare 1-4 → 直接對應）
        price_level = place.get("price", 0)

        # 營業時間
        hours_info = place.get("hours", {})
        opening_hours = hours_info.get("display", []) if isinstance(hours_info, dict) else []
        if isinstance(opening_hours, str):
            opening_hours = [opening_hours]

        # Google Maps 搜尋連結（免費，用地名和地址搜尋）
        name = place.get("name", "")
        query = urllib.parse.quote(f"{name} {address}")
        maps_url = f"https://www.google.com/maps/search/?api=1&query={query}"

        return {
            "place_id": place.get("fsq_id", ""),
            "name": name,
            "rating": rating,
            "category": category,
            "address": address,
            "maps_url": maps_url,
            "photo_url": photo_url,
            "reviews": [],
            "price_level": price_level,
            "opening_hours": opening_hours,
            "phone": place.get("tel", ""),
        }
