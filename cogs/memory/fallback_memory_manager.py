"""備用記憶體管理器

當向量資料庫被禁用時，提供替代的記憶體管理方案。
使用傳統的資料庫查詢和快取機制來實現記憶功能。
"""

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from .database import DatabaseManager
from .exceptions import MemorySystemError
from .search_engine import SearchQuery, SearchResult, SearchType, TimeRange
from function import func


@dataclass
class CacheEntry:
    """快取條目"""
    data: Any
    timestamp: datetime
    access_count: int = 0

    def is_expired(self, ttl_seconds: int) -> bool:
        """檢查條目是否過期"""
        return datetime.now() - self.timestamp > timedelta(seconds=ttl_seconds)


class FallbackMemoryManager:
    """備用記憶體管理器

    當向量資料庫被禁用時使用此管理器來處理記憶功能。
    使用基於關鍵字匹配、時間篩選和簡單的相似度計算。
    """

    def __init__(self, db_manager: DatabaseManager, cache_size: int = 1000, cache_ttl: int = 3600):
        """初始化備用記憶體管理器

        Args:
            db_manager: 資料庫管理器
            cache_size: 快取大小
            cache_ttl: 快取TTL（秒）
        """
        self.db_manager = db_manager
        self.cache_size = cache_size
        self.cache_ttl = cache_ttl
        self.logger = logging.getLogger(__name__)

        # 查詢快取
        self.query_cache: OrderedDict[str, CacheEntry] = OrderedDict()

        # 頻道訊息快取
        self.channel_cache: Dict[str, List[Dict[str, Any]]] = {}

        # 鎖定機制
        self._lock = asyncio.Lock()

        self.logger.info("FallbackMemoryManager 初始化完成")

    async def search_messages(
        self,
        query: SearchQuery,
        limit: int = 50
    ) -> SearchResult:
        """搜尋訊息（備用方案）

        Args:
            query: 搜尋查詢
            limit: 結果限制

        Returns:
            SearchResult: 搜尋結果
        """
        try:
            # 建立快取鍵
            cache_key = self._generate_cache_key(query)

            # 檢查快取
            if cache_key in self.query_cache:
                entry = self.query_cache[cache_key]
                if not entry.is_expired(self.cache_ttl):
                    entry.access_count += 1
                    self.query_cache.move_to_end(cache_key)
                    return entry.data

            # 從資料庫搜尋
            start_time = time.time()
            messages = await self._search_from_database(query, limit)
            search_time = time.time() - start_time

            # 建立搜尋結果
            result = SearchResult(
                query=query.query,
                messages=messages,
                total_results=len(messages),
                search_time=search_time,
                search_type=query.search_type,
                time_range=query.time_range,
                metadata={"fallback_mode": True}
            )

            # 快取結果
            await self._cache_result(cache_key, result)

            self.logger.debug(f"備用搜尋完成，找到 {len(messages)} 條訊息，耗時 {search_time:.3f}秒")
            return result

        except Exception as e:
            await func.report_error(e, "Fallback search")
            self.logger.error(f"備用搜尋失敗: {e}")
            raise MemorySystemError(f"備用記憶體搜尋失敗: {e}")

    async def _search_from_database(
        self,
        query: SearchQuery,
        limit: int
    ) -> List[Dict[str, Any]]:
        """從資料庫搜尋訊息

        Args:
            query: 搜尋查詢
            limit: 結果限制

        Returns:
            List[Dict[str, Any]]: 訊息列表
        """
        try:
            # 基本條件
            conditions = []
            params = []

            # 關鍵字搜尋
            if query.query and query.search_type in [SearchType.KEYWORD, SearchType.HYBRID]:
                conditions.append("(content LIKE ? OR author_name LIKE ?)")
                search_term = f"%{query.query}%"
                params.extend([search_term, search_term])

            # 頻道篩選
            if query.channel_id:
                conditions.append("channel_id = ?")
                params.append(query.channel_id)

            # 時間範圍篩選
            if query.time_range:
                if query.time_range.start_time:
                    conditions.append("timestamp >= ?")
                    params.append(query.time_range.start_time.isoformat())
                if query.time_range.end_time:
                    conditions.append("timestamp <= ?")
                    params.append(query.time_range.end_time.isoformat())

            # 用戶篩選
            if query.user_id:
                conditions.append("author_id = ?")
                params.append(str(query.user_id))

            # 構建查詢
            where_clause = " AND ".join(conditions) if conditions else "1=1"

            sql = f"""
                SELECT
                    id, channel_id, content, author_id, author_name,
                    timestamp, attachments, embeds, reactions
                FROM messages
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params.append(limit)

            # 執行查詢
            messages = await asyncio.get_event_loop().run_in_executor(
                None, self.db_manager.execute_query, sql, params
            )

            # 簡單的相關性排序（如果有搜尋詞）
            if query.query and query.search_type in [SearchType.SEMANTIC, SearchType.HYBRID]:
                messages = self._rank_by_relevance(messages, query.query)

            return messages[:limit]

        except Exception as e:
            await func.report_error(e, "Database search in fallback")
            self.logger.error(f"資料庫搜尋失敗: {e}")
            return []

    def _rank_by_relevance(self, messages: List[Dict[str, Any]], search_query: str) -> List[Dict[str, Any]]:
        """根據相關性對訊息進行排序

        Args:
            messages: 訊息列表
            search_query: 搜尋查詢

        Returns:
            List[Dict[str, Any]]: 排序後的訊息列表
        """
        def calculate_relevance(message: Dict[str, Any]) -> float:
            """計算訊息相關性分數"""
            content = message.get('content', '').lower()
            search_terms = search_query.lower().split()

            # 基本分數：完全匹配
            score = 0.0

            # 關鍵字匹配
            for term in search_terms:
                if term in content:
                    # 完全匹配得高分
                    if content == term:
                        score += 10.0
                    # 部分匹配
                    elif content.startswith(term) or content.endswith(term):
                        score += 5.0
                    else:
                        score += 2.0

            # 長度加權（較短的訊息相關性更高）
            content_length = len(content)
            if content_length > 0:
                score *= (1000 / content_length)  # 較短的訊息得分更高

            # 作者匹配加分
            author = message.get('author_name', '').lower()
            if any(term in author for term in search_terms):
                score += 3.0

            return score

        # 排序
        return sorted(messages, key=calculate_relevance, reverse=True)

    def _generate_cache_key(self, query: SearchQuery) -> str:
        """生成快取鍵

        Args:
            query: 搜尋查詢

        Returns:
            str: 快取鍵
        """
        key_parts = [
            str(query.search_type),
            query.query or "",
            query.channel_id or "",
            str(query.user_id or ""),
            str(query.time_range.start_time.timestamp() if query.time_range and query.time_range.start_time else ""),
            str(query.time_range.end_time.timestamp() if query.time_range and query.time_range.end_time else "")
        ]
        return "|".join(key_parts)

    async def _cache_result(self, cache_key: str, result: SearchResult) -> None:
        """快取搜尋結果

        Args:
            cache_key: 快取鍵
            result: 搜尋結果
        """
        async with self._lock:
            # 清理過期的快取條目
            expired_keys = [
                key for key, entry in self.query_cache.items()
                if entry.is_expired(self.cache_ttl)
            ]
            for key in expired_keys:
                del self.query_cache[key]

            # 如果快取已滿，移除最少使用的條目
            while len(self.query_cache) >= self.cache_size:
                oldest_key, _ = self.query_cache.popitem(last=False)
                self.logger.debug(f"移除過期的快取條目: {oldest_key}")

            # 添加新條目
            self.query_cache[cache_key] = CacheEntry(
                data=result,
                timestamp=datetime.now()
            )

            self.query_cache.move_to_end(cache_key)
            self.logger.debug(f"快取搜尋結果: {cache_key}")

    async def get_channel_messages(
        self,
        channel_id: str,
        limit: int = 100,
        before_message_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """取得頻道訊息

        Args:
            channel_id: 頻道ID
            limit: 限制數量
            before_message_id: 在此訊息ID之前的訊息

        Returns:
            List[Dict[str, Any]]: 訊息列表
        """
        try:
            # 檢查快取
            if channel_id in self.channel_cache:
                messages = self.channel_cache[channel_id]
                # 篩選條件
                if before_message_id:
                    messages = [msg for msg in messages if msg['id'] < before_message_id]
                return messages[:limit]

            # 從資料庫查詢
            conditions = ["channel_id = ?"]
            params = [channel_id]

            if before_message_id:
                conditions.append("id < ?")
                params.append(before_message_id)

            where_clause = " AND ".join(conditions)

            sql = f"""
                SELECT
                    id, channel_id, content, author_id, author_name,
                    timestamp, attachments, embeds, reactions
                FROM messages
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params.append(limit)

            messages = await asyncio.get_event_loop().run_in_executor(
                None, self.db_manager.execute_query, sql, params
            )

            # 更新快取
            self.channel_cache[channel_id] = messages

            return messages

        except Exception as e:
            await func.report_error(e, f"Channel message retrieval for {channel_id}")
            self.logger.error(f"取得頻道訊息失敗: {e}")
            return []

    async def add_message(self, message_data: Dict[str, Any]) -> bool:
        """添加訊息到記憶系統

        Args:
            message_data: 訊息資料

        Returns:
            bool: 是否成功
        """
        try:
            # 清除相關快取
            channel_id = message_data.get('channel_id')
            if channel_id and channel_id in self.channel_cache:
                del self.channel_cache[channel_id]

            # 清除查詢快取
            await self._clear_query_cache_for_channel(channel_id)

            self.logger.debug(f"訊息已添加到備用記憶系統: {channel_id}")
            return True

        except Exception as e:
            await func.report_error(e, "Message addition in fallback")
            self.logger.error(f"添加訊息到備用記憶系統失敗: {e}")
            return False

    async def _clear_query_cache_for_channel(self, channel_id: Optional[str]) -> None:
        """清除特定頻道的查詢快取

        Args:
            channel_id: 頻道ID
        """
        if not channel_id:
            return

        async with self._lock:
            keys_to_remove = [
                key for key in self.query_cache.keys()
                if channel_id in key
            ]
            for key in keys_to_remove:
                del self.query_cache[key]

    async def get_stats(self) -> Dict[str, Any]:
        """取得統計資訊

        Returns:
            Dict[str, Any]: 統計資料
        """
        async with self._lock:
            cache_entries = len(self.query_cache)
            channel_entries = len(self.channel_cache)

            # 計算快取命中率
            total_accesses = sum(entry.access_count for entry in self.query_cache.values())
            total_queries = len(self.query_cache)

            return {
                "fallback_mode": True,
                "cache_entries": cache_entries,
                "channel_cache_entries": channel_entries,
                "total_cache_accesses": total_accesses,
                "average_access_per_entry": total_accesses / total_queries if total_queries > 0 else 0,
                "cache_size_limit": self.cache_size
            }

    async def clear_cache(self) -> None:
        """清除所有快取"""
        async with self._lock:
            self.query_cache.clear()
            self.channel_cache.clear()
            self.logger.info("備用記憶體管理器快取已清除")

    async def shutdown(self) -> None:
        """關閉備用記憶體管理器"""
        await self.clear_cache()
        self.logger.info("FallbackMemoryManager 已關閉")