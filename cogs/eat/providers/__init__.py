"""餐廳搜尋 Provider 工廠

根據環境變數自動選擇最合適的 Provider：
- 有 FOURSQUARE_API_KEY → FoursquareProvider（免費 API，每月 1000 次）
- 否則 → GoogleMapCrawler fallback（Selenium 爬蟲，較慢但無費用限制）
"""
import os

from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="eat.providers")


def get_restaurant_provider():
    """返回最合適的餐廳搜尋 Provider 實例。"""
    api_key = os.getenv("FOURSQUARE_API_KEY")
    if api_key:
        from cogs.eat.providers.foursquare_provider import FoursquareProvider
        logger.info("使用 Foursquare Places API Provider")
        return FoursquareProvider(api_key=api_key)

    logger.warning("FOURSQUARE_API_KEY 未設定，fallback 到 Selenium 爬蟲（較慢且不穩定）")
    from cogs.eat.providers.googlemap_crawler import GoogleMapCrawler
    return _SeleniumFallbackProvider(GoogleMapCrawler())


class _SeleniumFallbackProvider:
    """將 GoogleMapCrawler 包裝為符合 Provider 介面的 fallback。"""

    def __init__(self, crawler):
        self._crawler = crawler

    async def async_search_list(self, keyword: str, lang: str = "zh_TW") -> list[dict]:
        return await self._crawler.async_search_list(keyword, lang)

    async def async_fetch_detail(self, url: str, lang: str = "zh_TW") -> dict:
        return await self._crawler.async_fetch_detail(url, lang)

    async def search(self, keyword: str, lang: str = "zh_TW") -> list[dict]:
        # 向後相容，預設執行 list 搜尋
        return await self.async_search_list(keyword, lang)

    async def close(self):
        try:
            self._crawler.close()
        except Exception:
            pass
