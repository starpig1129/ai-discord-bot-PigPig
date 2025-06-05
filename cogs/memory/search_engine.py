"""搜尋引擎模組

提供語義搜尋、相似度計算和搜尋結果處理功能。
支援搜尋快取、結果排序和過濾機制。
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from .config import MemoryProfile
from .embedding_service import EmbeddingService
from .exceptions import SearchError
from .vector_manager import VectorManager


class SearchType(Enum):
    """搜尋類型枚舉"""
    SEMANTIC = "semantic"  # 語義搜尋
    KEYWORD = "keyword"    # 關鍵字搜尋
    HYBRID = "hybrid"      # 混合搜尋


@dataclass
class TimeRange:
    """時間範圍資料類別"""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def contains(self, timestamp: datetime) -> bool:
        """檢查時間戳記是否在範圍內
        
        Args:
            timestamp: 要檢查的時間戳記
            
        Returns:
            bool: 是否在範圍內
        """
        if self.start_time and timestamp < self.start_time:
            return False
        if self.end_time and timestamp > self.end_time:
            return False
        return True


@dataclass
class SearchQuery:
    """搜尋查詢資料類別"""
    text: str
    channel_id: str
    search_type: SearchType = SearchType.SEMANTIC
    time_range: Optional[TimeRange] = None
    limit: int = 10
    score_threshold: float = 0.0
    include_metadata: bool = False
    filters: Dict[str, Any] = field(default_factory=dict)
    
    def get_cache_key(self) -> str:
        """產生快取鍵值
        
        Returns:
            str: 快取鍵值
        """
        # 建立查詢的唯一標識
        query_data = {
            "text": self.text,
            "channel_id": self.channel_id,
            "search_type": self.search_type.value,
            "limit": self.limit,
            "score_threshold": self.score_threshold,
            "time_range": {
                "start": self.time_range.start_time.isoformat() if self.time_range and self.time_range.start_time else None,
                "end": self.time_range.end_time.isoformat() if self.time_range and self.time_range.end_time else None
            } if self.time_range else None,
            "filters": sorted(self.filters.items()) if self.filters else []
        }
        
        query_str = str(query_data)
        return hashlib.md5(query_str.encode()).hexdigest()


@dataclass
class SearchResult:
    """搜尋結果資料類別"""
    messages: List[Dict[str, Any]]
    relevance_scores: List[float]
    total_found: int
    search_time_ms: float
    search_method: str
    cache_hit: bool = False
    query_vector: Optional[np.ndarray] = None
    
    def get_top_results(self, limit: int) -> 'SearchResult':
        """取得前 N 個結果
        
        Args:
            limit: 結果數量限制
            
        Returns:
            SearchResult: 限制後的搜尋結果
        """
        if limit >= len(self.messages):
            return self
        
        return SearchResult(
            messages=self.messages[:limit],
            relevance_scores=self.relevance_scores[:limit],
            total_found=self.total_found,
            search_time_ms=self.search_time_ms,
            search_method=self.search_method,
            cache_hit=self.cache_hit
        )


class SearchCache:
    """搜尋快取管理器"""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """初始化搜尋快取
        
        Args:
            max_size: 最大快取數量
            ttl_seconds: 快取存活時間（秒）
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[SearchResult, datetime]] = {}
        self.logger = logging.getLogger(__name__)
    
    def get(self, cache_key: str) -> Optional[SearchResult]:
        """從快取取得搜尋結果
        
        Args:
            cache_key: 快取鍵值
            
        Returns:
            Optional[SearchResult]: 快取的搜尋結果，如果不存在或過期則為 None
        """
        if cache_key in self._cache:
            result, timestamp = self._cache[cache_key]
            
            # 檢查是否過期
            if datetime.now() - timestamp < timedelta(seconds=self.ttl_seconds):
                result.cache_hit = True
                self.logger.debug(f"快取命中: {cache_key}")
                return result
            else:
                # 刪除過期快取
                del self._cache[cache_key]
                self.logger.debug(f"快取過期: {cache_key}")
        
        return None
    
    def put(self, cache_key: str, result: SearchResult) -> None:
        """將搜尋結果存入快取
        
        Args:
            cache_key: 快取鍵值
            result: 搜尋結果
        """
        # 如果快取已滿，刪除最舊的項目
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
            self.logger.debug(f"快取已滿，刪除最舊項目: {oldest_key}")
        
        self._cache[cache_key] = (result, datetime.now())
        self.logger.debug(f"快取已更新: {cache_key}")
    
    def clear(self) -> None:
        """清除所有快取"""
        self._cache.clear()
        self.logger.info("搜尋快取已清除")
    
    def get_stats(self) -> Dict[str, Union[int, float]]:
        """取得快取統計資訊
        
        Returns:
            Dict[str, Union[int, float]]: 快取統計
        """
        return {
            "cache_size": len(self._cache),
            "max_size": self.max_size,
            "usage_ratio": len(self._cache) / self.max_size,
            "ttl_seconds": self.ttl_seconds
        }


class SearchEngine:
    """搜尋引擎核心類別
    
    整合語義搜尋、向量管理和結果處理功能。
    """
    
    def __init__(
        self,
        profile: MemoryProfile,
        embedding_service: EmbeddingService,
        vector_manager: VectorManager,
        enable_cache: bool = True
    ):
        """初始化搜尋引擎
        
        Args:
            profile: 記憶系統配置檔案
            embedding_service: 嵌入服務
            vector_manager: 向量管理器
            enable_cache: 是否啟用快取
        """
        self.logger = logging.getLogger(__name__)
        self.profile = profile
        self.embedding_service = embedding_service
        self.vector_manager = vector_manager
        
        # 初始化快取
        if enable_cache:
            cache_size = getattr(profile, 'cache_size_mb', 512) * 1000 // 10  # 估算快取項目數
            self.cache = SearchCache(max_size=cache_size, ttl_seconds=3600)
        else:
            self.cache = None
        
        # 搜尋統計
        self._search_count = 0
        self._total_search_time = 0.0
        self._cache_hits = 0
        
        self.logger.info(f"搜尋引擎初始化完成 - 快取: {enable_cache}")
    
    def search(self, query: SearchQuery) -> SearchResult:
        """執行搜尋
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
            
        Raises:
            SearchError: 搜尋失敗
        """
        start_time = time.time()
        
        try:
            # 檢查快取
            if self.cache:
                cache_key = query.get_cache_key()
                cached_result = self.cache.get(cache_key)
                if cached_result:
                    self._cache_hits += 1
                    return cached_result
            
            # 根據搜尋類型執行搜尋
            if query.search_type == SearchType.SEMANTIC:
                result = self._semantic_search(query)
            elif query.search_type == SearchType.KEYWORD:
                result = self._keyword_search(query)
            elif query.search_type == SearchType.HYBRID:
                result = self._hybrid_search(query)
            else:
                raise SearchError(f"不支援的搜尋類型: {query.search_type}")
            
            # 計算搜尋時間
            search_time = (time.time() - start_time) * 1000
            result.search_time_ms = search_time
            
            # 更新統計
            self._search_count += 1
            self._total_search_time += search_time
            
            # 存入快取
            if self.cache:
                self.cache.put(cache_key, result)
            
            self.logger.debug(
                f"搜尋完成 - 類型: {query.search_type.value}, "
                f"結果: {len(result.messages)}, 耗時: {search_time:.1f}ms"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"搜尋失敗: {e}")
            raise SearchError(f"搜尋執行失敗: {e}")
    
    def _semantic_search(self, query: SearchQuery) -> SearchResult:
        """執行語義搜尋
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
        """
        if not self.profile.vector_enabled:
            return SearchResult(
                messages=[],
                relevance_scores=[],
                total_found=0,
                search_time_ms=0.0,
                search_method="semantic_disabled"
            )
        
        # 生成查詢向量
        query_vector = self.embedding_service.encode_text(query.text)
        
        # 向量搜尋
        vector_results = self.vector_manager.search_similar(
            channel_id=query.channel_id,
            query_vector=query_vector,
            k=query.limit * 2,  # 取更多結果用於後續過濾
            score_threshold=query.score_threshold
        )
        
        # 轉換結果格式（這裡需要從資料庫取得完整訊息資料）
        messages = []
        scores = []
        
        for message_id, similarity_score in vector_results:
            # 這裡應該從資料庫取得完整的訊息資料
            # 暫時使用簡化格式
            message_data = {
                "message_id": message_id,
                "similarity_score": similarity_score,
                # 其他欄位需要從資料庫查詢
            }
            messages.append(message_data)
            scores.append(similarity_score)
        
        # 應用時間過濾
        if query.time_range:
            filtered_messages = []
            filtered_scores = []
            
            for msg, score in zip(messages, scores):
                # 需要從訊息資料中取得時間戳記進行過濾
                # 暫時跳過時間過濾
                filtered_messages.append(msg)
                filtered_scores.append(score)
            
            messages = filtered_messages
            scores = filtered_scores
        
        # 限制結果數量
        if len(messages) > query.limit:
            messages = messages[:query.limit]
            scores = scores[:query.limit]
        
        return SearchResult(
            messages=messages,
            relevance_scores=scores,
            total_found=len(vector_results),
            search_time_ms=0.0,  # 將在主搜尋函數中設定
            search_method="semantic",
            query_vector=query_vector
        )
    
    def _keyword_search(self, query: SearchQuery) -> SearchResult:
        """執行關鍵字搜尋
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
        """
        # 關鍵字搜尋需要整合資料庫的全文檢索功能
        # 這裡提供介面，實際實作在第三階段
        
        self.logger.debug(f"關鍵字搜尋: {query.text}")
        
        return SearchResult(
            messages=[],
            relevance_scores=[],
            total_found=0,
            search_time_ms=0.0,
            search_method="keyword_placeholder"
        )
    
    def _hybrid_search(self, query: SearchQuery) -> SearchResult:
        """執行混合搜尋
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
        """
        # 混合搜尋結合語義和關鍵字搜尋
        # 目前先實作語義搜尋部分
        
        semantic_result = self._semantic_search(query)
        # keyword_result = self._keyword_search(query)
        
        # 合併和排序結果（在第三階段完整實作）
        return SearchResult(
            messages=semantic_result.messages,
            relevance_scores=semantic_result.relevance_scores,
            total_found=semantic_result.total_found,
            search_time_ms=0.0,
            search_method="hybrid_partial"
        )
    
    def calculate_similarity(
        self, 
        text1: str, 
        text2: str
    ) -> float:
        """計算兩個文本的相似度
        
        Args:
            text1: 第一個文本
            text2: 第二個文本
            
        Returns:
            float: 相似度分數 (0-1)
        """
        try:
            if not self.profile.vector_enabled:
                return 0.0
            
            vectors = self.embedding_service.encode_batch([text1, text2])
            if len(vectors) != 2:
                return 0.0
            
            # 計算餘弦相似度
            vec1, vec2 = vectors[0], vectors[1]
            
            # 正規化向量
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            cosine_sim = np.dot(vec1, vec2) / (norm1 * norm2)
            
            # 確保結果在 [0, 1] 範圍內
            return max(0.0, min(1.0, (cosine_sim + 1.0) / 2.0))
            
        except Exception as e:
            self.logger.error(f"計算相似度失敗: {e}")
            return 0.0
    
    def get_statistics(self) -> Dict[str, Union[int, float]]:
        """取得搜尋引擎統計資訊
        
        Returns:
            Dict[str, Union[int, float]]: 統計資訊
        """
        avg_search_time = (
            self._total_search_time / self._search_count 
            if self._search_count > 0 else 0.0
        )
        
        cache_hit_rate = (
            self._cache_hits / self._search_count 
            if self._search_count > 0 else 0.0
        )
        
        stats = {
            "total_searches": self._search_count,
            "total_search_time_ms": self._total_search_time,
            "average_search_time_ms": avg_search_time,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": cache_hit_rate
        }
        
        # 加入快取統計
        if self.cache:
            stats.update(self.cache.get_stats())
        
        return stats
    
    def clear_cache(self) -> None:
        """清除搜尋快取"""
        if self.cache:
            self.cache.clear()
            self.logger.info("搜尋引擎快取已清除")
    
    def optimize_performance(self) -> Dict[str, Any]:
        """優化搜尋效能
        
        Returns:
            Dict[str, Any]: 優化結果報告
        """
        optimization_report = {
            "cache_cleared": False,
            "indices_optimized": []
        }
        
        try:
            # 清除過期快取
            if self.cache:
                old_size = len(self.cache._cache)
                # 手動清理過期項目
                current_time = datetime.now()
                expired_keys = [
                    key for key, (_, timestamp) in self.cache._cache.items()
                    if current_time - timestamp >= timedelta(seconds=self.cache.ttl_seconds)
                ]
                
                for key in expired_keys:
                    del self.cache._cache[key]
                
                new_size = len(self.cache._cache)
                optimization_report["cache_cleared"] = old_size > new_size
                optimization_report["expired_items_removed"] = old_size - new_size
            
            self.logger.info("搜尋引擎效能優化完成")
            
        except Exception as e:
            self.logger.error(f"搜尋引擎優化失敗: {e}")
            optimization_report["error"] = str(e)
        
        return optimization_report