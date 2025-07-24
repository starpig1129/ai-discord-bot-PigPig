"""搜尋引擎模組

提供語義搜尋、相似度計算和搜尋結果處理功能。
支援搜尋快取、結果排序和過濾機制。
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import discord
import numpy as np

from .config import MemoryProfile
from .embedding_service import EmbeddingService
from .exceptions import SearchError
from .vector_manager import VectorManager
from .reranker_service import RerankerService


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
        bot,  # 新增 bot 實例
        reranker_service: Optional[RerankerService] = None,
        cache: Optional[SearchCache] = None,
        enable_reranker: bool = True
    ):
        """初始化搜尋引擎
        
        Args:
            profile: 記憶系統配置檔案
            embedding_service: 嵌入服務
            vector_manager: 向量管理器
            database_manager: 資料庫管理器
            bot: Discord bot 實例
            reranker_service: 重排序服務實例
            cache: 搜尋快取實例
            enable_reranker: 是否啟用重排序
        """
        self.logger = logging.getLogger(__name__)
        self.profile = profile
        self.embedding_service = embedding_service
        self.vector_manager = vector_manager
        self.database_manager = database_manager
        self.bot = bot
        self.reranker_service = reranker_service
        self.cache = cache

        # 初始化重排序服務
        self.enable_reranker = (
            enable_reranker and
            profile.vector_enabled and
            self.reranker_service is not None
        )
        if self.enable_reranker:
            self.logger.info("重排序服務已啟用")
        else:
            self.reranker_service = None
            self.logger.info("重排序服務已停用")
        
        # 搜尋統計
        self._search_count = 0
        self._total_search_time = 0.0
        self._rerank_count = 0
        
        self.logger.info(
            f"搜尋引擎初始化完成 - 重排序: {self.enable_reranker}"
        )
    
    async def search(self, query: SearchQuery) -> SearchResult:
        """執行搜尋的核心邏輯，不包含快取。
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
            
        Raises:
            SearchError: 搜尋失敗
        """
        start_time = time.time()
        
        try:
            # 根據搜尋類型執行搜尋
            if query.search_type == SearchType.SEMANTIC:
                result = await self._semantic_search(query)
            elif query.search_type == SearchType.KEYWORD:
                result = self._keyword_search(query)
            elif query.search_type == SearchType.TEMPORAL:
                result = await self._temporal_search(query)
            elif query.search_type == SearchType.HYBRID:
                result = await self._hybrid_search(query)
            else:
                raise SearchError(f"不支援的搜尋類型: {query.search_type}")
            
            # 計算搜尋時間
            search_time = (time.time() - start_time) * 1000
            result.search_time_ms = search_time
            
            # 更新內部統計
            self._search_count += 1
            self._total_search_time += search_time
            
            self.logger.debug(
                f"搜尋執行完成 - 類型: {query.search_type.value}, "
                f"結果: {len(result.messages)}, 耗時: {search_time:.1f}ms"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"搜尋失敗: {e}")
            raise SearchError(f"搜尋執行失敗: {e}")
    
    async def _semantic_search(self, query: SearchQuery) -> SearchResult:
        """執行語義搜尋
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
        """
        if not self.profile.vector_enabled:
            return SearchResult(
                messages=[], relevance_scores=[], total_found=0,
                search_time_ms=0.0, search_method="semantic_disabled"
            )

        query_vector = self.embedding_service.encode_text(query.text)
        
        vector_results = self.vector_manager.search_similar(
            channel_id=query.channel_id, query_vector=query_vector,
            k=query.limit * 3, score_threshold=query.score_threshold
        )
        
        if not vector_results:
            return SearchResult(
                messages=[], relevance_scores=[], total_found=0,
                search_time_ms=0.0, search_method="semantic_no_results",
                query_vector=query_vector
            )

        segment_ids = [seg_id for seg_id, _ in vector_results]
        segment_score_map = {seg_id: score for seg_id, score in vector_results}

        segment_to_message_map = self.database_manager.get_segment_to_message_map(segment_ids)
        
        all_message_ids = [
            msg_id for seg_id in segment_ids
            for msg_id in segment_to_message_map.get(seg_id, [])
        ]
        unique_message_ids = list(dict.fromkeys(all_message_ids))

        if not unique_message_ids:
            self.logger.warning("語義搜尋找到片段，但無法對應到任何訊息。")
            return SearchResult(
                messages=[], relevance_scores=[], total_found=0,
                search_time_ms=0.0, search_method="semantic_no_messages",
                query_vector=query_vector
            )

        db_messages = self.database_manager.get_messages_by_ids(unique_message_ids)
        message_map = {msg['message_id']: msg for msg in db_messages}

        # 識別資料庫中完全缺失的 ID
        found_message_ids = set(message_map.keys())
        missing_ids = set(unique_message_ids) - found_message_ids
        if missing_ids:
            self.logger.debug(f"本地查詢遺失 {len(missing_ids)} 個 IDs: {missing_ids}")
        
        db_missing_ids = {msg_id for msg_id in unique_message_ids if msg_id not in message_map}

        # 識別資料庫中存在但內容無效的 ID
        invalid_ids = set()
        for msg_id, msg in message_map.items():
            content = msg.get('content', '')
            content_processed = msg.get('content_processed', '')
            has_valid_content = (content and content.strip()) or \
                                (content_processed and content_processed.strip() and content_processed != 'None')
            if not has_valid_content:
                invalid_ids.add(msg_id)
        
        # 合併所有需要從 Discord 獲取的 ID
        ids_to_fetch = list(db_missing_ids.union(invalid_ids))

        if ids_to_fetch:
            self.logger.info(f"在本地資料庫中找不到或內容無效，需要從 Discord 回退 {len(ids_to_fetch)} 則訊息。")
            fetched_messages = await asyncio.gather(
                *[self._fetch_message_from_discord(query.channel_id, msg_id) for msg_id in ids_to_fetch]
            )
            for msg_data in fetched_messages:
                if msg_data:
                    # 無論如何都更新/覆蓋 message_map 中的資料
                    message_map[msg_data['message_id']] = msg_data

        message_to_segment_map = {
            msg_id: seg_id 
            for seg_id, msg_ids in segment_to_message_map.items() 
            for msg_id in msg_ids
        }

        messages, scores = [], []
        for message_id in unique_message_ids:
            if message_id in message_map:
                message_data = message_map[message_id].copy()
                
                content = message_data.get('content', '')
                content_processed = message_data.get('content_processed', '')
                has_valid_content = (content and content.strip()) or \
                                    (content_processed and content_processed.strip() and content_processed != 'None')

                if has_valid_content:
                    segment_id = message_to_segment_map.get(message_id)
                    similarity_score = segment_score_map.get(segment_id, 0.0)
                    
                    message_data['similarity_score'] = similarity_score
                    messages.append(message_data)
                    scores.append(similarity_score)
                else:
                    self.logger.debug(f"跳過空內容訊息 ID: {message_id}")
            else:
                self.logger.warning(f"在資料庫和 Discord 中都找不到訊息 ID: {message_id}")

        if query.time_range:
            filtered_messages, filtered_scores = [], []
            for msg, score in zip(messages, scores):
                try:
                    if 'timestamp' in msg and msg['timestamp']:
                        timestamp = msg['timestamp']
                        if isinstance(timestamp, str):
                            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        
                        if query.time_range.contains(timestamp):
                            filtered_messages.append(msg)
                            filtered_scores.append(score)
                    else:
                        filtered_messages.append(msg)
                        filtered_scores.append(score)
                except Exception as e:
                    self.logger.warning(f"處理時間過濾失敗: {e}")
                    filtered_messages.append(msg)
                    filtered_scores.append(score)
            messages, scores = filtered_messages, filtered_scores

        search_method = "semantic"
        if self.enable_reranker and self.reranker_service and messages:
            try:
                rerank_count = min(len(messages), query.limit * 2)
                rerank_messages = messages[:rerank_count]
                
                reranked_messages = self.reranker_service.rerank_results(
                    query=query.text,
                    candidates=rerank_messages,
                    score_field="content_processed" if (rerank_messages and rerank_messages[0].get("content_processed")) else "content",
                    top_k=query.limit
                )
                
                messages = reranked_messages
                scores = [msg.get("rerank_score", msg.get("similarity_score", 0.0)) for msg in messages]
                self._rerank_count += 1
                search_method = "semantic_with_rerank"
                self.logger.debug(f"重排序完成，處理了 {rerank_count} 個候選，返回 {len(messages)} 個結果")
            except Exception as e:
                self.logger.warning(f"重排序失敗，使用原始結果: {e}")

        if len(messages) > query.limit:
            messages = messages[:query.limit]
            scores = scores[:query.limit]
        
        return SearchResult(
            messages=messages,
            relevance_scores=scores,
            total_found=len(unique_message_ids),
            search_time_ms=0.0,
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
        self.logger.debug(f"開始關鍵字搜尋: {query.text}")
        
        try:
            # 使用 jieba 分詞提取關鍵字
            keywords = self._extract_keywords(query.text)
            
            if not keywords:
                self.logger.warning(f"無法從查詢中提取關鍵字: {query.text}")
                return SearchResult(
                    messages=[],
                    relevance_scores=[],
                    total_found=0,
                    search_time_ms=0.0,
                    search_method="keyword_no_keywords"
                )
            
            self.logger.debug(f"提取的關鍵字: {keywords}")
            
            # 計算時間範圍
            before_time = None
            after_time = None
            if query.time_range:
                before_time = query.time_range.end_time
                after_time = query.time_range.start_time
            
            # 從資料庫搜尋
            messages = self.database_manager.search_messages_by_keywords(
                channel_id=query.channel_id,
                keywords=keywords,
                limit=query.limit * 2,  # 取更多結果以便後續過濾
                before=before_time,
                after=after_time
            )
            
            # 過濾空內容的訊息
            filtered_messages = []
            scores = []
            
            for message in messages:
                content = message.get('content', '')
                content_processed = message.get('content_processed', '')
                
                # 檢查是否有有效內容
                has_valid_content = (
                    (content and content.strip()) or
                    (content_processed and content_processed.strip() and content_processed != 'None')
                )
                
                if has_valid_content:
                    # 重新計算匹配分數（更精確的算法）
                    match_score = self._calculate_enhanced_keyword_score(
                        content, content_processed, keywords, query.text
                    )
                    message['keyword_score'] = match_score
                    
                    filtered_messages.append(message)
                    scores.append(match_score)
                else:
                    self.logger.debug(f"跳過空內容訊息 ID: {message.get('message_id')}")
            
            # 按分數排序
            if filtered_messages:
                sorted_pairs = sorted(
                    zip(filtered_messages, scores),
                    key=lambda x: x[1],
                    reverse=True
                )
                filtered_messages, scores = zip(*sorted_pairs)
                filtered_messages = list(filtered_messages)
                scores = list(scores)
            
            # 限制結果數量
            if len(filtered_messages) > query.limit:
                filtered_messages = filtered_messages[:query.limit]
                scores = scores[:query.limit]
            
            # 應用分數閾值過濾
            if query.score_threshold > 0:
                threshold_filtered = []
                threshold_scores = []
                
                for msg, score in zip(filtered_messages, scores):
                    if score >= query.score_threshold:
                        threshold_filtered.append(msg)
                        threshold_scores.append(score)
                
                filtered_messages = threshold_filtered
                scores = threshold_scores
            
            self.logger.info(
                f"關鍵字搜尋完成 - 關鍵字: {keywords}, "
                f"結果: {len(filtered_messages)}/{len(messages)}"
            )
            
            return SearchResult(
                messages=filtered_messages,
                relevance_scores=scores,
                total_found=len(messages),
                search_time_ms=0.0,  # 將在主搜尋函數中設定
                search_method="keyword"
            )
            
        except Exception as e:
            self.logger.error(f"關鍵字搜尋失敗: {e}")
            return SearchResult(
                messages=[],
                relevance_scores=[],
                total_found=0,
                search_time_ms=0.0,
                search_method="keyword_error"
            )
    
    def _extract_keywords(self, text: str) -> List[str]:
        """從文本中提取關鍵字
        
        Args:
            text: 輸入文本
            
        Returns:
            List[str]: 關鍵字列表
        """
        try:
            import jieba
            import jieba.analyse
            
            # 清理文本
            cleaned_text = text.strip()
            if not cleaned_text:
                return []
            
            # 使用 jieba 分詞
            words = jieba.lcut(cleaned_text)
            
            # 過濾關鍵字
            keywords = []
            stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一個', '上', '也', '很', '到', '說', '要', '去', '你', '會', '著', '沒有', '看', '好', '自己', '這', '那', '什麼', '可以', '這個', '來', '用', '她', '他', '我們', '它', '這些', '那些', '但是', '如果', '因為', '所以', '然後', '還是', '或者', '而且', '不過', '雖然', '但', '與', '及', '以及', '等', '等等', '之類', '之類的', '，', '。', '！', '？', '；', '：', '"', '"', ''', ''', '（', '）', '【', '】', '《', '》', '、', '…', '——', '—', '-', '_', '=', '+', '*', '/', '\\', '|', '&', '%', '$', '#', '@', '!', '?', '.', ',', ';', ':', '"', "'", '(', ')', '[', ']', '{', '}', '<', '>', '~', '`'}
            
            for word in words:
                # 過濾條件
                if word.strip() and word not in stop_words and not word.isdigit():
                    keywords.append(word)
            
            # 如果沒有提取到關鍵字，使用 TF-IDF 作為備用
            if not keywords:
                self.logger.debug("使用 TF-IDF 提取關鍵字")
                keywords = jieba.analyse.extract_tags(cleaned_text, topK=5)
            
            return list(set(keywords))  # 返回唯一的關鍵字
            
        except ImportError:
            self.logger.warning("jieba 模組未安裝，關鍵字搜尋功能受限。")
            return text.split()
        except Exception as e:
            self.logger.error(f"提取關鍵字失敗: {e}")
            return text.split()

    def _calculate_enhanced_keyword_score(
        self, content: str, content_processed: Optional[str], keywords: List[str], query: str
    ) -> float:
        """計算增強的關鍵字匹配分數
        
        Args:
            content: 原始訊息內容
            content_processed: 處理後的訊息內容
            keywords: 關鍵字列表
            query: 原始查詢字串
            
        Returns:
            float: 匹配分數 (0.0 - 1.0)
        """
        total_score = 0.0
        matched_keywords = 0
        
        # 優先使用處理後的內容
        search_text = content_processed if content_processed and content_processed.strip() else content
        search_text_lower = search_text.lower()
        query_lower = query.lower()
        
        # 完整查詢匹配加分
        if query_lower in search_text_lower:
            total_score += 0.3
        
        # 關鍵字匹配
        if keywords:
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in search_text_lower:
                    matched_keywords += 1
                    keyword_score = 0.1  # 基礎分
                    
                    # 根據關鍵字長度加權
                    if len(keyword) >= 2:
                        keyword_score += 0.05
                    if len(keyword) >= 3:
                        keyword_score += 0.05
                    
                    total_score += keyword_score
                    self.logger.debug(f"關鍵字匹配: '{keyword}' -> {keyword_score:.3f}")
            
            # 匹配關鍵字比例加分
            match_ratio = matched_keywords / len(keywords)
            total_score += match_ratio * 0.2
        
        # 正規化分數
        final_score = min(total_score, 1.0)
        
        self.logger.debug(
            f"關鍵字分數計算: {matched_keywords}/{len(keywords)} 匹配, "
            f"最終分數: {final_score:.3f}"
        )
        
        return final_score
    
    async def _temporal_search(self, query: SearchQuery) -> SearchResult:
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
            return await self._semantic_search(query)
        else:
            # 如果沒有時間範圍，回退到語義搜尋
            self.logger.warning("時間搜尋但沒有提供時間範圍，回退到語義搜尋")
            return await self._semantic_search(query)

    async def _hybrid_search(self, query: SearchQuery) -> SearchResult:
        """執行混合搜尋
        
        結合語義搜尋和關鍵字搜尋的結果。
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
        """
        self.logger.debug(f"開始混合搜尋: {query.text}")
        
        try:
            # 1. 執行語義搜尋 (非同步)
            semantic_task = asyncio.create_task(self._semantic_search(
                SearchQuery(
                    text=query.text,
                    channel_id=query.channel_id,
                    limit=query.limit * 2,
                    score_threshold=query.score_threshold,
                    time_range=query.time_range
                )
            ))
            
            # 2. 執行關鍵字搜尋 (同步，在執行器中運行以避免阻塞)
            loop = asyncio.get_running_loop()
            keyword_results = await loop.run_in_executor(
                None,  # 使用預設執行器
                self._keyword_search,
                SearchQuery(
                    text=query.text,
                    channel_id=query.channel_id,
                    limit=query.limit * 2,
                    score_threshold=0.1,
                    time_range=query.time_range
                )
            )

            semantic_results = await semantic_task
            
            # 3. 合併和重新排序結果
            combined_messages = {}
            
            # 處理語義搜尋結果
            if semantic_results and semantic_results.messages:
                for i, msg in enumerate(semantic_results.messages):
                    msg_id = msg['message_id']
                    combined_messages[msg_id] = {
                        "message": msg,
                        "semantic_score": semantic_results.relevance_scores[i],
                        "keyword_score": 0.0
                    }
            
            # 處理關鍵字搜尋結果
            if keyword_results and keyword_results.messages:
                for i, msg in enumerate(keyword_results.messages):
                    msg_id = msg['message_id']
                    if msg_id in combined_messages:
                        combined_messages[msg_id]['keyword_score'] = keyword_results.relevance_scores[i]
                    else:
                        combined_messages[msg_id] = {
                            "message": msg,
                            "semantic_score": 0.0,
                            "keyword_score": keyword_results.relevance_scores[i]
                        }
            
            # 計算混合分數並排序
            final_results = []
            for msg_id, data in combined_messages.items():
                semantic_score = data['semantic_score']
                keyword_score = data['keyword_score']
                
                # 混合分數權重
                hybrid_score = (semantic_score * 0.6) + (keyword_score * 0.4)
                if semantic_score > 0 and keyword_score > 0:
                    hybrid_score += 0.1  # 獎勵同時匹配
                
                message_data = data['message']
                message_data['hybrid_score'] = min(hybrid_score, 1.0)
                final_results.append((message_data, hybrid_score))
            
            # 按混合分數降序排序
            final_results.sort(key=lambda x: x[1], reverse=True)
            
            # 提取排序後的訊息和分數
            messages = [item[0] for item in final_results[:query.limit]]
            scores = [item[1] for item in final_results[:query.limit]]
            
            return SearchResult(
                messages=messages,
                relevance_scores=scores,
                total_found=len(combined_messages),
                search_time_ms=0.0,  # 將在主函數中設定
                search_method="hybrid"
            )
            
        except Exception as e:
            self.logger.error(f"混合搜尋失敗: {e}", exc_info=True)
            return SearchResult(
                messages=[],
                relevance_scores=[],
                total_found=0,
                search_time_ms=0.0,
                search_method="hybrid_error"
            )

    def calculate_similarity(
        self, text1: str, text2: str, model: Optional[str] = None
    ) -> float:
        """計算兩個文本的相似度
        
        Args:
            text1: 第一個文本
            text2: 第二個文本
            model: 使用的嵌入模型
            
        Returns:
            float: 相似度分數
        """
        try:
            vec1 = self.embedding_service.encode_text(text1, model=model)
            vec2 = self.embedding_service.encode_text(text2, model=model)
            
            # 計算餘弦相似度
            similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
            return float(similarity)
            
        except Exception as e:
            self.logger.error(f"計算相似度失敗: {e}")
            return 0.0

    def get_statistics(self) -> Dict[str, Union[int, float]]:
        """取得搜尋引擎的統計資訊
        
        Returns:
            Dict[str, Union[int, float]]: 統計資訊字典
        """
        avg_search_time = (self._total_search_time / self._search_count) if self._search_count > 0 else 0.0
        
        stats = {
            "total_searches": self._search_count,
            "total_search_time_ms": self._total_search_time,
            "average_search_time_ms": avg_search_time,
            "reranked_searches": self._rerank_count,
            "cache_stats": self.cache.get_stats() if self.cache else {}
        }
        
        # 添加向量管理器統計
        if self.vector_manager:
            stats["vector_manager_stats"] = self.vector_manager.get_statistics()
            
        return stats

    def clear_cache(self) -> None:
        """清除搜尋快取
        
        提供一個方便的方法來清除快取，而無需直接訪問快取對象。
        """
        if self.cache:
            self.cache.clear()
            self.logger.info("搜尋快取已成功清除")
        else:
            self.logger.warning("未配置搜尋快取，無法清除")

    def optimize_performance(self) -> Dict[str, Any]:
        """優化搜尋效能
        
        執行諸如清理過期快取、預熱模型等操作。
        
        Returns:
            Dict[str, Any]: 優化操作的報告
        """
        optimization_report = {"status": "success"}
        self.logger.info("開始搜尋引擎效能優化...")
        
        try:
            # 1. 清理過期快取
            if self.cache:
                old_size = len(self.cache._cache)
                expired_keys = [
                    k for k, (_, ts) in self.cache._cache.items()
                    if datetime.now() - ts > timedelta(seconds=self.cache.ttl_seconds)
                ]
                for key in expired_keys:
                    del self.cache._cache[key]
                
                new_size = len(self.cache._cache)
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
    
    async def _fetch_message_from_discord(self, channel_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        """從 Discord API 獲取訊息並存入資料庫"""
        try:
            # 將 ID 轉換為整數
            channel_id_int = int(channel_id)
            message_id_int = int(message_id)

            channel = self.bot.get_channel(channel_id_int)
            if not channel:
                self.logger.warning(f"找不到頻道: {channel_id}")
                return None
            
            # 確保 channel 是可以發送訊息的文字頻道
            if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
                 self.logger.warning(f"頻道 {channel_id} 不是有效的文字頻道，無法獲取訊息。")
                 return None

            message = await channel.fetch_message(message_id_int)
            if not message:
                return None

            # 將 discord.Message 物件轉換為資料庫格式
            message_data = {
                'message_id': str(message.id),
                'channel_id': str(message.channel.id),
                'user_id': str(message.author.id),
                'content': message.content,
                'timestamp': message.created_at,
                'message_type': 'user', # 預設類型
                'content_processed': None,
                'metadata': None
            }
            
            # 異步存入資料庫
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, self.database_manager.store_message, **message_data
            )
            
            self.logger.debug(f"[DEBUG_SEARCH] Discord 回退: 成功獲取 message_id={message_id}")
            self.logger.info(f"從 Discord 回退成功並儲存訊息: {message_id}")
            
            # 返回從 message 物件轉換的字典，而不是 store_message 的結果
            return {
                'message_id': str(message.id),
                'channel_id': str(message.channel.id),
                'user_id': str(message.author.id),
                'content': message.content,
                'timestamp': message.created_at,
                'content_processed': None,
                'metadata': None
            }

        except (discord.NotFound, ValueError):
            self.logger.warning(f"[DEBUG_SEARCH] Discord 回退: 獲取 message_id={message_id} 失敗: 訊息不存在 (NotFound) 或 ID 格式錯誤")
            self.logger.warning(f"在 Discord 上找不到訊息 ID: {message_id} 或 ID 格式錯誤")
            return None
        except discord.Forbidden:
            self.logger.warning(f"[DEBUG_SEARCH] Discord 回退: 獲取 message_id={message_id} 失敗: 沒有權限 (Forbidden)")
            self.logger.error(f"沒有權限獲取訊息 ID: {message_id} (頻道: {channel_id})")
            return None
        except Exception as e:
            self.logger.warning(f"[DEBUG_SEARCH] Discord 回退: 獲取 message_id={message_id} 失敗: {e}")
            self.logger.error(f"從 Discord 獲取訊息時發生未知錯誤 (訊息 ID: {message_id}): {e}", exc_info=True)
            return None

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