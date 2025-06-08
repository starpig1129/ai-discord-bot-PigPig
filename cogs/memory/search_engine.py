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
from .reranker_service import RerankerService, reranker_service_manager


class SearchType(Enum):
    """搜尋類型枚舉"""
    SEMANTIC = "semantic"  # 語義搜尋
    KEYWORD = "keyword"    # 關鍵字搜尋
    TEMPORAL = "temporal"  # 時間搜尋
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
    threshold: float = 0.7
    user_id: Optional[str] = None
    
    def get_cache_key(self) -> str:
        """產生快取鍵值
        
        Returns:
            str: 快取鍵值
        """
        threshold_value = getattr(self, 'threshold', self.score_threshold)
        
        # 建立查詢的唯一標識
        query_data = {
            "text": self.text,
            "channel_id": self.channel_id,
            "search_type": self.search_type.value,
            "limit": self.limit,
            "score_threshold": threshold_value,
            "time_range": {
                "start": self.time_range.start_time.isoformat() if self.time_range and self.time_range.start_time else None,
                "end": self.time_range.end_time.isoformat() if self.time_range and self.time_range.end_time else None
            } if self.time_range else None,
            "filters": sorted(self.filters.items()) if self.filters else [],
            "user_id": getattr(self, 'user_id', None)  # 兼容性字段
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
    
    整合語義搜尋、向量管理、重排序和結果處理功能。
    """
    
    def __init__(
        self,
        profile: MemoryProfile,
        embedding_service: EmbeddingService,
        vector_manager: VectorManager,
        database_manager,
        enable_cache: bool = True,
        enable_reranker: bool = True
    ):
        """初始化搜尋引擎
        
        Args:
            profile: 記憶系統配置檔案
            embedding_service: 嵌入服務
            vector_manager: 向量管理器
            database_manager: 資料庫管理器
            enable_cache: 是否啟用快取
            enable_reranker: 是否啟用重排序
        """
        self.logger = logging.getLogger(__name__)
        self.profile = profile
        self.embedding_service = embedding_service
        self.vector_manager = vector_manager
        self.database_manager = database_manager
        
        # 初始化重排序服務
        self.enable_reranker = enable_reranker and profile.vector_enabled
        if self.enable_reranker:
            try:
                self.reranker_service = reranker_service_manager.get_service(profile)
                self.logger.info("重排序服務已啟用")
            except Exception as e:
                self.logger.warning(f"重排序服務初始化失敗，已停用: {e}")
                self.enable_reranker = False
                self.reranker_service = None
        else:
            self.reranker_service = None
            self.logger.info("重排序服務已停用")
        
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
        self._rerank_count = 0
        
        self.logger.info(
            f"搜尋引擎初始化完成 - 快取: {enable_cache}, "
            f"重排序: {self.enable_reranker}"
        )
    
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
            elif query.search_type == SearchType.TEMPORAL:
                result = self._temporal_search(query)
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
        
        # 向量搜尋 - 取更多結果以補償空內容過濾
        vector_results = self.vector_manager.search_similar(
            channel_id=query.channel_id,
            query_vector=query_vector,
            k=query.limit * 3,  # 增加倍數以補償空內容過濾
            score_threshold=query.score_threshold
        )
        
        # 轉換結果格式（從資料庫取得完整訊息資料）
        messages = []
        scores = []
        
        if vector_results:
            # 批次查詢訊息資料以提高效能
            message_ids = [message_id for message_id, _ in vector_results]
            try:
                # 從資料庫取得完整訊息資料
                db_messages = self.database_manager.get_messages_by_ids(message_ids)
                
                # 建立 message_id 到訊息資料的映射
                message_map = {msg['message_id']: msg for msg in db_messages}
                
                # 按照向量搜尋結果的順序組織資料，並過濾空內容
                for message_id, similarity_score in vector_results:
                    if message_id in message_map:
                        message_data = message_map[message_id].copy()
                        
                        # 過濾空內容的訊息
                        content = message_data.get('content', '')
                        content_processed = message_data.get('content_processed', '')
                        
                        # 檢查是否有有效內容（不為空且不只是空白）
                        has_valid_content = (
                            (content and content.strip()) or
                            (content_processed and content_processed.strip() and content_processed != 'None')
                        )
                        
                        if has_valid_content:
                            message_data['similarity_score'] = similarity_score
                            messages.append(message_data)
                            scores.append(similarity_score)
                        else:
                            self.logger.debug(f"跳過空內容訊息 ID: {message_id} (content: {repr(content)}, processed: {repr(content_processed)})")
                    else:
                        self.logger.warning(f"在資料庫中找不到訊息 ID: {message_id}")
                        
            except Exception as e:
                self.logger.error(f"從資料庫查詢訊息失敗: {e}")
                # 降級處理：使用簡化格式
                for message_id, similarity_score in vector_results:
                    message_data = {
                        "message_id": message_id,
                        "similarity_score": similarity_score,
                        "content": f"[無法載入訊息內容: {e}]",
                        "user_id": "unknown",
                        "channel_id": query.channel_id,
                        "timestamp": None
                    }
                    messages.append(message_data)
                    scores.append(similarity_score)
        
        # 應用時間過濾
        if query.time_range:
            filtered_messages = []
            filtered_scores = []
            
            for msg, score in zip(messages, scores):
                # 從訊息資料中取得時間戳記進行過濾
                try:
                    if 'timestamp' in msg and msg['timestamp']:
                        # 處理時間戳記格式
                        if isinstance(msg['timestamp'], str):
                            from datetime import datetime
                            timestamp = datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00'))
                        else:
                            timestamp = msg['timestamp']
                        
                        # 檢查是否在時間範圍內
                        if query.time_range.contains(timestamp):
                            filtered_messages.append(msg)
                            filtered_scores.append(score)
                    else:
                        # 如果沒有時間戳記，保留訊息（向後相容）
                        filtered_messages.append(msg)
                        filtered_scores.append(score)
                except Exception as e:
                    self.logger.warning(f"處理時間過濾失敗: {e}")
                    # 發生錯誤時保留訊息
                    filtered_messages.append(msg)
                    filtered_scores.append(score)
            
            messages = filtered_messages
            scores = filtered_scores
        
        # 應用重排序（在限制結果數量之前）
        if self.enable_reranker and self.reranker_service and messages:
            try:
                # 取更多結果用於重排序（最多 query.limit * 2）
                rerank_count = min(len(messages), query.limit * 2)
                rerank_messages = messages[:rerank_count]
                
                # 執行重排序
                reranked_messages = self.reranker_service.rerank_results(
                    query=query.text,
                    candidates=rerank_messages,
                    score_field="content_processed" if (rerank_messages and
                                                       isinstance(rerank_messages[0], dict) and
                                                       rerank_messages[0].get("content_processed")) else "content",
                    top_k=query.limit
                )
                
                # 更新消息和分數
                messages = reranked_messages
                scores = [msg.get("rerank_score", msg.get("similarity_score", 0.0)) for msg in messages]
                
                self._rerank_count += 1
                search_method = "semantic_with_rerank"
                
                self.logger.debug(f"重排序完成，處理了 {rerank_count} 個候選，返回 {len(messages)} 個結果")
                
            except Exception as e:
                self.logger.warning(f"重排序失敗，使用原始結果: {e}")
                search_method = "semantic"
        else:
            search_method = "semantic"
        
        # 限制結果數量（如果重排序沒有限制的話）
        if len(messages) > query.limit:
            messages = messages[:query.limit]
            scores = scores[:query.limit]
        
        return SearchResult(
            messages=messages,
            relevance_scores=scores,
            total_found=len(vector_results),
            search_time_ms=0.0,  # 將在主搜尋函數中設定
            search_method=search_method,
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
    
    def _temporal_search(self, query: SearchQuery) -> SearchResult:
        """執行時間搜尋
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
        """
        # 時間搜尋主要基於時間範圍篩選
        # 可以結合關鍵字或語義搜尋
        
        if query.time_range:
            # 如果有時間範圍，執行時間篩選的語義搜尋
            return self._semantic_search(query)
        else:
            # 如果沒有時間範圍，回退到語義搜尋
            self.logger.warning("時間搜尋但沒有提供時間範圍，回退到語義搜尋")
            return self._semantic_search(query)
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
        
        # 混合搜尋：結合語義搜尋和重排序
        if self.enable_reranker and self.reranker_service and semantic_result.messages:
            try:
                # 對語義搜尋結果進行重排序
                reranked_messages = self.reranker_service.rerank_results(
                    query=query.text,
                    candidates=semantic_result.messages,
                    score_field="content_processed" if (semantic_result.messages and
                                                       isinstance(semantic_result.messages[0], dict) and
                                                       semantic_result.messages[0].get("content_processed")) else "content",
                    top_k=query.limit
                )
                
                # 計算混合分數（結合語義分數和重排序分數）
                hybrid_scores = []
                for msg in reranked_messages:
                    semantic_score = msg.get("similarity_score", 0.0)
                    rerank_score = msg.get("rerank_score", 0.0)
                    # 加權組合：70% 重排序分數 + 30% 語義分數
                    hybrid_score = 0.7 * rerank_score + 0.3 * semantic_score
                    hybrid_scores.append(hybrid_score)
                
                self._rerank_count += 1
                
                return SearchResult(
                    messages=reranked_messages,
                    relevance_scores=hybrid_scores,
                    total_found=semantic_result.total_found,
                    search_time_ms=0.0,
                    search_method="hybrid_with_rerank"
                )
                
            except Exception as e:
                self.logger.warning(f"混合搜尋重排序失敗，使用語義結果: {e}")
        
        # 降級處理：返回語義搜尋結果
        return SearchResult(
            messages=semantic_result.messages,
            relevance_scores=semantic_result.relevance_scores,
            total_found=semantic_result.total_found,
            search_time_ms=0.0,
            search_method="hybrid_semantic_only"
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
            "cache_hit_rate": cache_hit_rate,
            "rerank_enabled": self.enable_reranker,
            "total_reranks": self._rerank_count
        }
        
        # 加入快取統計
        if self.cache:
            stats.update(self.cache.get_stats())
        
        # 加入重排序統計
        if self.enable_reranker and self.reranker_service:
            reranker_stats = self.reranker_service.get_statistics()
            stats["reranker_stats"] = reranker_stats
        
        return stats
    
    def clear_cache(self) -> None:
        """清除搜尋快取"""
        if self.cache:
            self.cache.clear()
            self.logger.info("搜尋引擎快取已清除")
        
        # 清除重排序快取
        if self.enable_reranker and self.reranker_service:
            self.reranker_service.clear_cache()
            self.logger.info("重排序服務快取已清除")
    
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
    
    def warmup_reranker(self) -> None:
        """預熱重排序模型"""
        if self.enable_reranker and self.reranker_service:
            try:
                self.reranker_service.warmup()
                self.logger.info("重排序模型預熱完成")
            except Exception as e:
                self.logger.warning(f"重排序模型預熱失敗: {e}")
        else:
            self.logger.debug("重排序服務未啟用，跳過預熱")
    
    def set_reranker_enabled(self, enabled: bool) -> None:
        """動態啟用/停用重排序功能
        
        Args:
            enabled: 是否啟用重排序
        """
        if enabled and not self.enable_reranker and self.profile.vector_enabled:
            try:
                self.reranker_service = reranker_service_manager.get_service(self.profile)
                self.enable_reranker = True
                self.logger.info("重排序服務已啟用")
            except Exception as e:
                self.logger.error(f"啟用重排序服務失敗: {e}")
        elif not enabled and self.enable_reranker:
            self.enable_reranker = False
            if self.reranker_service:
                self.reranker_service.clear_cache()
            self.logger.info("重排序服務已停用")
    
    def cleanup(self) -> None:
        """清理搜尋引擎資源和快取
        
        執行完整的清理作業，清除快取並釋放相關資源。
        """
        try:
            self.logger.info("開始搜尋引擎清理...")
            
            # 清除搜尋快取
            self.clear_cache()
            
            # 清理重排序服務
            if self.enable_reranker and self.reranker_service:
                try:
                    if hasattr(self.reranker_service, 'cleanup'):
                        self.reranker_service.cleanup()
                    else:
                        self.reranker_service.clear_cache()
                    self.logger.info("重排序服務已清理")
                except Exception as e:
                    self.logger.warning(f"清理重排序服務失敗: {e}")
            
            # 重置統計資料
            self._search_count = 0
            self._total_search_time = 0.0
            self._cache_hits = 0
            self._rerank_count = 0
            
            # 強制垃圾回收
            import gc
            gc.collect()
            
            self.logger.info("搜尋引擎清理完成")
            
        except Exception as e:
            self.logger.error(f"搜尋引擎清理時發生錯誤: {e}")