"""記憶系統核心管理器

實作 Discord 頻道記憶系統的核心功能，包括記憶存儲、檢索和管理。
提供統一的 API 接口供 Discord bot 使用。
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import discord
import numpy as np

from .database import DatabaseManager
from .config import MemoryConfig, MemoryProfile
from .embedding_service import EmbeddingService, embedding_service_manager
from .vector_manager import VectorManager
from .search_engine import SearchEngine, SearchQuery as EngineSearchQuery, SearchResult as EngineSearchResult, SearchType as EngineSearchType, TimeRange
from .exceptions import (
    MemorySystemError,
    DatabaseError,
    ConfigurationError,
    SearchError,
    VectorOperationError
)


class SearchType(Enum):
    """搜尋類型枚舉"""
    SEMANTIC = "semantic"      # 語義搜尋
    KEYWORD = "keyword"        # 關鍵字搜尋
    TEMPORAL = "temporal"      # 時間搜尋
    HYBRID = "hybrid"          # 混合搜尋


@dataclass
class SearchQuery:
    """搜尋查詢資料類別"""
    text: str
    channel_id: str
    search_type: SearchType = SearchType.HYBRID
    limit: int = 10
    threshold: float = 0.7
    time_range: Optional[Tuple[datetime, datetime]] = None
    include_metadata: bool = False
    user_id: Optional[str] = None


@dataclass
class SearchResult:
    """搜尋結果資料類別"""
    messages: List[Dict[str, Any]]
    relevance_scores: List[float]
    total_found: int
    search_time_ms: int
    search_method: str
    cache_hit: bool = False
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MemoryStats:
    """記憶系統統計資料"""
    total_channels: int
    total_messages: int
    vector_enabled_channels: int
    average_query_time_ms: float
    cache_hit_rate: float
    storage_size_mb: float


class MemoryManager:
    """記憶系統管理器
    
    負責管理 Discord 頻道的永久記憶功能，包括訊息存儲、
    搜尋檢索、配置管理和性能監控。
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化記憶管理器
        
        Args:
            config_path: 配置檔案路徑
        """
        self.logger = logging.getLogger(__name__)
        self._initialized = False
        self._enabled = False
        
        # 配置管理
        self.config = MemoryConfig(config_path)
        self.current_profile: Optional[MemoryProfile] = None
        
        # 資料庫管理
        self.db_manager: Optional[DatabaseManager] = None
        
        # 向量搜尋組件
        self.embedding_service: Optional[EmbeddingService] = None
        self.vector_manager: Optional[VectorManager] = None
        self.search_engine: Optional[SearchEngine] = None
        
        # 性能統計
        self._query_times: List[float] = []
        self._cache_hits = 0
        self._cache_misses = 0
        
        # 執行緒安全鎖
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> bool:
        """初始化記憶系統
        
        Returns:
            bool: 是否成功初始化
        """
        if self._initialized:
            return True
        
        try:
            self.logger.info("開始初始化記憶系統...")
            
            # 載入配置
            await self._load_configuration()
            
            # 檢查是否啟用記憶系統
            memory_config = self.config.get_memory_config()
            self._enabled = memory_config.get("enabled", True)
            
            if not self._enabled:
                self.logger.info("記憶系統已停用")
                return False
            
            # 初始化資料庫
            await self._initialize_database()
            
            # 載入配置檔案
            self.current_profile = self.config.get_current_profile()
            
            # 初始化向量組件
            await self._initialize_vector_components()
            
            self._initialized = True
            self.logger.info(f"記憶系統初始化完成 (配置檔案: {self.current_profile.name})")
            
            return True
            
        except Exception as e:
            self.logger.error(f"記憶系統初始化失敗: {e}")
            raise MemorySystemError(f"記憶系統初始化失敗: {e}")
    
    async def _load_configuration(self) -> None:
        """載入配置"""
        try:
            # 在非同步環境中執行配置載入
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.config.load_config)
            
        except Exception as e:
            raise ConfigurationError(f"載入配置失敗: {e}")
    
    async def _initialize_database(self) -> None:
        """初始化資料庫"""
        try:
            memory_config = self.config.get_memory_config()
            db_path = memory_config.get("database_path", "data/memory/memory.db")
            
            # 在執行緒池中初始化資料庫
            loop = asyncio.get_event_loop()
            self.db_manager = await loop.run_in_executor(
                None, 
                DatabaseManager, 
                db_path
            )
            
        except Exception as e:
            raise DatabaseError(f"初始化資料庫失敗: {e}")
    
    async def _initialize_vector_components(self) -> None:
        """初始化向量搜尋組件"""
        try:
            if not self.current_profile.vector_enabled:
                self.logger.info("向量搜尋功能已停用")
                return
            
            # 在執行緒池中初始化向量組件
            loop = asyncio.get_event_loop()
            
            # 初始化嵌入服務
            self.embedding_service = await loop.run_in_executor(
                None,
                embedding_service_manager.get_service,
                self.current_profile
            )
            
            # 初始化向量管理器
            memory_config = self.config.get_memory_config()
            storage_path = memory_config.get("database_path", "data/memory/memory.db")
            indices_path = Path(storage_path).parent / "indices"
            
            self.vector_manager = await loop.run_in_executor(
                None,
                VectorManager,
                self.current_profile,
                indices_path
            )
            
            # 初始化搜尋引擎
            self.search_engine = await loop.run_in_executor(
                None,
                SearchEngine,
                self.current_profile,
                self.embedding_service,
                self.vector_manager,
                self.db_manager,
                memory_config.get("cache", {}).get("enabled", True)
            )
            
            # 預熱嵌入模型
            await loop.run_in_executor(None, self.embedding_service.warmup)
            
            # 載入現有的索引檔案
            await self._load_existing_indices()
            
            self.logger.info("向量搜尋組件初始化完成")
            
        except Exception as e:
            self.logger.error(f"初始化向量組件失敗: {e}")
            # 不拋出例外，允許系統在無向量功能的情況下運行
            self.current_profile.vector_enabled = False
    
    async def _load_existing_indices(self) -> None:
        """載入現有的索引檔案到記憶體中"""
        try:
            if not self.vector_manager or not self.current_profile.vector_enabled:
                return
            
            # 取得索引目錄
            indices_path = self.vector_manager.storage_path
            if not indices_path.exists():
                self.logger.info("索引目錄不存在，跳過載入現有索引")
                return
            
            # 搜尋所有 .index 檔案
            index_files = list(indices_path.glob("*.index"))
            if not index_files:
                self.logger.info("沒有找到現有的索引檔案")
                return
            
            self.logger.info(f"找到 {len(index_files)} 個現有索引檔案，開始載入...")
            
            # 載入索引檔案
            loop = asyncio.get_event_loop()
            loaded_count = 0
            failed_count = 0
            
            for index_file in index_files:
                try:
                    # 從檔案名稱取得頻道 ID
                    channel_id = index_file.stem
                    
                    # 在執行緒池中載入索引
                    success = await loop.run_in_executor(
                        None,
                        self.vector_manager.create_channel_index,
                        channel_id
                    )
                    
                    if success:
                        loaded_count += 1
                        self.logger.debug(f"成功載入頻道 {channel_id} 的索引")
                    else:
                        failed_count += 1
                        self.logger.warning(f"載入頻道 {channel_id} 的索引失敗")
                        
                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"載入索引檔案 {index_file.name} 失敗: {e}")
            
            self.logger.info(
                f"索引載入完成: {loaded_count} 個成功，{failed_count} 個失敗，"
                f"總共 {loaded_count + failed_count} 個索引檔案"
            )
            
        except Exception as e:
            self.logger.error(f"載入現有索引失敗: {e}")
    
    async def store_message(self, message: discord.Message) -> bool:
        """儲存 Discord 訊息
        
        Args:
            message: Discord 訊息物件
            
        Returns:
            bool: 是否成功儲存
        """
        if not self._check_initialized():
            return False
        
        try:
            async with self._lock:
                # 準備訊息資料
                message_data = self._prepare_message_data(message)
                
                # 在執行緒池中執行資料庫操作
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    None,
                    self._store_message_sync,
                    message_data
                )
                
                if success:
                    # 如果啟用向量功能，生成並儲存嵌入向量
                    if self.current_profile.vector_enabled and self.embedding_service and self.vector_manager:
                        await self._store_message_vector(message_data)
                    
                    self.logger.debug(f"成功儲存訊息: {message.id}")
                
                return success
                
        except Exception as e:
            self.logger.error(f"儲存訊息失敗: {e}")
            raise MemorySystemError(f"儲存訊息失敗: {e}")
    
    def _prepare_message_data(self, message: discord.Message) -> Dict[str, Any]:
        """準備訊息資料
        
        Args:
            message: Discord 訊息物件
            
        Returns:
            Dict[str, Any]: 處理後的訊息資料
        """
        # 處理訊息內容
        content = message.content or ""
        content_processed = self._preprocess_content(content)
        
        # 確定訊息類型
        message_type = "bot" if message.author.bot else "user"
        
        # 建立元資料
        metadata = {
            "author_name": message.author.display_name,
            "user_id": str(message.author.id),
            "has_attachments": len(message.attachments) > 0,
            "has_embeds": len(message.embeds) > 0,
            "reply_to": str(message.reference.message_id) if message.reference else None
        }
        
        return {
            "message_id": str(message.id),
            "channel_id": str(message.channel.id),
            "user_id": str(message.author.id),
            "content": content,
            "content_processed": content_processed,
            "timestamp": message.created_at,  # 保持為 datetime 物件
            "message_type": message_type,
            "metadata": json.dumps(metadata, ensure_ascii=False) if metadata else None
        }
    
    def _preprocess_content(self, content: str) -> str:
        """預處理訊息內容
        
        Args:
            content: 原始內容
            
        Returns:
            str: 處理後的內容
        """
        if not content:
            return ""
        
        # 移除 Discord 格式化標記
        import re
        
        # 移除 mentions
        content = re.sub(r'<@!?\d+>', '', content)
        content = re.sub(r'<#\d+>', '', content)
        content = re.sub(r'<@&\d+>', '', content)
        
        # 移除自定義 emoji
        content = re.sub(r'<:\w+:\d+>', '', content)
        
        # 移除 URL
        content = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', content)
        
        # 清理多餘空白
        content = ' '.join(content.split())
        
        return content.strip()
    
    def _store_message_sync(self, message_data: Dict[str, Any]) -> bool:
        """同步儲存訊息 (在執行緒池中執行)
        
        Args:
            message_data: 訊息資料
            
        Returns:
            bool: 是否成功儲存
        """
        try:
            return self.db_manager.store_message(**message_data)
        except Exception as e:
            self.logger.error(f"同步儲存訊息失敗: {e}")
            return False
    
    async def _store_message_vector(self, message_data: Dict[str, Any]) -> None:
        """儲存訊息的向量嵌入
        
        Args:
            message_data: 訊息資料
        """
        try:
            # 檢查是否有有效的內容
            content = message_data.get("content_processed", "") or message_data.get("content", "")
            if not content.strip():
                return
            
            channel_id = message_data["channel_id"]
            message_id = message_data["message_id"]
            
            # 確保頻道索引存在
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.vector_manager.create_channel_index,
                channel_id
            )
            
            # 生成嵌入向量
            embedding = await loop.run_in_executor(
                None,
                self.embedding_service.encode_text,
                content
            )
            
            # 儲存向量到 FAISS 索引
            faiss_success = await loop.run_in_executor(
                None,
                self.vector_manager.add_vectors,
                channel_id,
                embedding.reshape(1, -1),  # 轉換為批次格式
                [message_id]
            )
            
            # 儲存嵌入到資料庫
            db_success = await loop.run_in_executor(
                None,
                self._store_embedding_to_database,
                message_id,
                channel_id,
                embedding,
                self.current_profile.embedding_model,
                len(embedding)
            )
            
            # 定期儲存索引檔案（每 50 個向量儲存一次）
            if faiss_success:
                try:
                    # 取得頻道的向量統計
                    stats = self.vector_manager.get_index_stats(channel_id)
                    total_vectors = stats.get("total_vectors", 0)
                    
                    # 每 50 個向量或第一個向量時儲存索引
                    if total_vectors == 1 or total_vectors % 50 == 0:
                        save_success = await loop.run_in_executor(
                            None,
                            self.vector_manager.save_index,
                            channel_id
                        )
                        if save_success:
                            self.logger.debug(f"頻道 {channel_id} 索引檔案已儲存（向量數: {total_vectors}）")
                        else:
                            self.logger.warning(f"頻道 {channel_id} 索引檔案儲存失敗")
                except Exception as e:
                    self.logger.warning(f"定期儲存索引檔案失敗: {e}")
            
            if faiss_success and db_success:
                self.logger.debug(f"向量嵌入已儲存到索引和資料庫: {message_id}")
            elif faiss_success:
                self.logger.warning(f"向量嵌入儲存到索引成功，但資料庫儲存失敗: {message_id}")
            elif db_success:
                self.logger.warning(f"向量嵌入儲存到資料庫成功，但索引儲存失敗: {message_id}")
            else:
                self.logger.warning(f"向量嵌入儲存完全失敗: {message_id}")
                
        except Exception as e:
            self.logger.error(f"儲存訊息向量失敗: {e}")
            # 不拋出例外，避免影響主要的訊息儲存流程
    
    def _store_embedding_to_database(
        self,
        message_id: str,
        channel_id: str,
        embedding: np.ndarray,
        model_version: str,
        dimension: int
    ) -> bool:
        """將嵌入向量儲存到資料庫
        
        Args:
            message_id: 訊息 ID
            channel_id: 頻道 ID
            embedding: 嵌入向量
            model_version: 模型版本
            dimension: 向量維度
            
        Returns:
            bool: 是否成功儲存
        """
        try:
            # 生成嵌入 ID
            embedding_id = f"{message_id}_{uuid.uuid4().hex[:8]}"
            
            # 序列化向量資料
            vector_data = embedding.tobytes()
            
            with self.db_manager.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO embeddings
                    (embedding_id, message_id, channel_id, vector_data, model_version, dimension)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (embedding_id, message_id, channel_id, vector_data, model_version, dimension))
                conn.commit()
            
            self.logger.debug(f"嵌入向量已儲存到資料庫: {message_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"儲存嵌入向量到資料庫失敗: {e}")
            return False
    
    async def search_memory(self, query: SearchQuery) -> SearchResult:
        """搜尋記憶
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
        """
        if not self._check_initialized():
            return SearchResult(
                messages=[],
                relevance_scores=[],
                total_found=0,
                search_time_ms=0,
                search_method="disabled"
            )
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # 目前階段只實作基本的關鍵字搜尋
            # 後續階段會加入向量搜尋和混合搜尋
            if query.search_type == SearchType.SEMANTIC and not self.current_profile.vector_enabled:
                # 如果要求語義搜尋但向量功能未啟用，降級為關鍵字搜尋
                query.search_type = SearchType.KEYWORD
            
            result = await self._perform_search(query)
            
            # 記錄搜尋時間
            search_time_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
            result.search_time_ms = search_time_ms
            
            self._query_times.append(search_time_ms)
            if len(self._query_times) > 1000:  # 保持最近 1000 次查詢的記錄
                self._query_times.pop(0)
            
            return result
            
        except Exception as e:
            self.logger.error(f"搜尋記憶失敗: {e}")
            raise SearchError(f"搜尋記憶失敗: {e}", search_type=query.search_type.value, query=query.text)
    
    async def _perform_search(self, query: SearchQuery) -> SearchResult:
        """執行搜尋操作
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
        """
        # 如果有搜尋引擎且啟用向量功能，使用新的搜尋引擎
        if self.search_engine and query.search_type in [SearchType.SEMANTIC, SearchType.HYBRID]:
            return await self._semantic_search_with_engine(query)
        
        # 回退到基本搜尋
        return await self._basic_search(query)
    
    async def _semantic_search_with_engine(self, query: SearchQuery) -> SearchResult:
        """使用搜尋引擎執行語義搜尋
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
        """
        try:
            # 轉換搜尋查詢格式，保持原有的搜尋類型
            engine_search_type = EngineSearchType.SEMANTIC
            if query.search_type == SearchType.HYBRID:
                engine_search_type = EngineSearchType.HYBRID
            
            engine_query = EngineSearchQuery(
                text=query.text,
                channel_id=query.channel_id,
                search_type=engine_search_type,
                time_range=TimeRange(
                    start_time=query.time_range[0] if query.time_range else None,
                    end_time=query.time_range[1] if query.time_range else None
                ) if query.time_range else None,
                limit=query.limit,
                score_threshold=query.threshold,
                include_metadata=query.include_metadata
            )
            
            # 在執行緒池中執行搜尋
            loop = asyncio.get_event_loop()
            engine_result = await loop.run_in_executor(
                None,
                self.search_engine.search,
                engine_query
            )
            
            # 從向量搜尋結果中取得完整的訊息資料
            messages = await self._enrich_search_results(engine_result.messages)
            
            # 轉換回原有格式
            return SearchResult(
                messages=messages,
                relevance_scores=engine_result.relevance_scores,
                total_found=engine_result.total_found,
                search_time_ms=int(engine_result.search_time_ms),
                search_method=engine_result.search_method,
                cache_hit=engine_result.cache_hit
            )
            
        except Exception as e:
            self.logger.error(f"語義搜尋失敗: {e}")
            # 回退到關鍵字搜尋
            fallback_query = SearchQuery(
                text=query.text,
                channel_id=query.channel_id,
                search_type=SearchType.KEYWORD,
                limit=query.limit,
                threshold=query.threshold,
                time_range=query.time_range,
                include_metadata=query.include_metadata,
                user_id=query.user_id
            )
            return await self._basic_search(fallback_query)
    
    async def _basic_search(self, query: SearchQuery) -> SearchResult:
        """執行基本搜尋（關鍵字/時間）
        
        Args:
            query: 搜尋查詢
            
        Returns:
            SearchResult: 搜尋結果
        """
        # 執行關鍵字/時間搜尋
        loop = asyncio.get_event_loop()
        messages = await loop.run_in_executor(
            None,
            self._keyword_search_sync,
            query
        )
        
        # 計算簡單的相關性分數 (基於關鍵字匹配)
        relevance_scores = self._calculate_keyword_relevance(messages, query.text)
        
        return SearchResult(
            messages=messages,
            relevance_scores=relevance_scores,
            total_found=len(messages),
            search_time_ms=0,  # 會在上層設定
            search_method="keyword"
        )
    
    def _keyword_search_sync(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """同步關鍵字搜尋
        
        Args:
            query: 搜尋查詢
            
        Returns:
            List[Dict[str, Any]]: 搜尋結果
        """
        try:
            # 取得時間範圍
            before = query.time_range[1] if query.time_range else None
            after = query.time_range[0] if query.time_range else None
            
            # 從資料庫取得訊息
            messages = self.db_manager.get_messages(
                channel_id=query.channel_id,
                limit=query.limit * 2,  # 取更多訊息進行過濾
                before=before,
                after=after
            )
            
            # 過濾包含關鍵字的訊息
            if query.text.strip():
                filtered_messages = []
                keywords = query.text.lower().split()
                
                for message in messages:
                    content = ((message.get("content") or "") + " " +
                              (message.get("content_processed") or "")).lower()
                    
                    # 檢查是否包含任何關鍵字
                    if any(keyword in content for keyword in keywords):
                        filtered_messages.append(message)
                        
                        if len(filtered_messages) >= query.limit:
                            break
                
                return filtered_messages
            
            return messages[:query.limit]
            
        except Exception as e:
            self.logger.error(f"關鍵字搜尋失敗: {e}")
            return []
    
    def _calculate_keyword_relevance(self, messages: List[Dict[str, Any]], query_text: str) -> List[float]:
        """計算關鍵字相關性分數
        
        Args:
            messages: 訊息列表
            query_text: 查詢文字
            
        Returns:
            List[float]: 相關性分數列表
        """
        if not query_text.strip():
            return [1.0] * len(messages)
        
        keywords = query_text.lower().split()
        scores = []
        
        for message in messages:
            content = ((message.get("content") or "") + " " +
                      (message.get("content_processed") or "")).lower()
            
            # 計算關鍵字匹配分數
            matches = sum(1 for keyword in keywords if keyword in content)
            score = matches / len(keywords) if keywords else 0.0
            scores.append(min(score, 1.0))
        
        return scores
    
    async def _enrich_search_results(self, vector_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """豐富向量搜尋結果，從資料庫取得完整訊息資料
        
        Args:
            vector_results: 向量搜尋結果
            
        Returns:
            List[Dict[str, Any]]: 完整的訊息資料
        """
        if not vector_results:
            return []
        
        try:
            # 提取訊息 ID
            message_ids = [result.get("message_id") for result in vector_results if result.get("message_id")]
            
            if not message_ids:
                return []
            
            # 從資料庫批次查詢訊息
            loop = asyncio.get_event_loop()
            enriched_messages = await loop.run_in_executor(
                None,
                self._get_messages_by_ids,
                message_ids
            )
            
            # 保持原有的排序（按相似度）
            message_dict = {msg["message_id"]: msg for msg in enriched_messages}
            ordered_messages = []
            
            for result in vector_results:
                message_id = result.get("message_id")
                if message_id in message_dict:
                    message = message_dict[message_id]
                    
                    # 過濾空內容的訊息
                    content = message.get('content', '')
                    content_processed = message.get('content_processed', '')
                    
                    # 檢查是否有有效內容（不為空且不只是空白）
                    has_valid_content = (
                        (content and content.strip()) or
                        (content_processed and content_processed.strip() and content_processed != 'None')
                    )
                    
                    if has_valid_content:
                        message["similarity_score"] = result.get("similarity_score", 0.0)
                        ordered_messages.append(message)
                    else:
                        self.logger.debug(f"記憶管理器跳過空內容訊息 ID: {message_id} (content: {repr(content)}, processed: {repr(content_processed)})")
            
            return ordered_messages
            
        except Exception as e:
            self.logger.error(f"豐富搜尋結果失敗: {e}")
            return []
    
    def _get_messages_by_ids(self, message_ids: List[str]) -> List[Dict[str, Any]]:
        """根據訊息 ID 批次查詢訊息
        
        Args:
            message_ids: 訊息 ID 列表
            
        Returns:
            List[Dict[str, Any]]: 訊息資料列表
        """
        try:
            # 使用資料庫管理器的正確實作
            return self.db_manager.get_messages_by_ids(message_ids)
        except Exception as e:
            self.logger.error(f"批次查詢訊息失敗: {e}")
            return []
    
    async def search_similar_messages(
        self, 
        channel_id: str, 
        query_text: str, 
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[Tuple[Dict[str, Any], float]]:
        """搜尋相似訊息（語義搜尋）
        
        Args:
            channel_id: 頻道 ID
            query_text: 查詢文本
            limit: 結果數量限制
            threshold: 相似度閾值
            
        Returns:
            List[Tuple[Dict[str, Any], float]]: [(訊息資料, 相似度分數), ...]
        """
        if not self._check_initialized() or not self.current_profile.vector_enabled:
            self.logger.debug("向量搜尋功能未啟用")
            return []
        
        try:
            # 建立語義搜尋查詢
            query = SearchQuery(
                text=query_text,
                channel_id=channel_id,
                search_type=SearchType.SEMANTIC,
                limit=limit,
                threshold=threshold
            )
            
            # 執行搜尋
            result = await self.search_memory(query)
            
            # 組合結果
            similar_messages = []
            for message, score in zip(result.messages, result.relevance_scores):
                similar_messages.append((message, score))
            
            return similar_messages
            
        except Exception as e:
            self.logger.error(f"搜尋相似訊息失敗: {e}")
            return []
    
    async def get_context(self, channel_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """取得頻道上下文
        
        Args:
            channel_id: 頻道 ID
            limit: 數量限制
            
        Returns:
            List[Dict[str, Any]]: 訊息列表
        """
        if not self._check_initialized():
            return []
        
        try:
            loop = asyncio.get_event_loop()
            messages = await loop.run_in_executor(
                None,
                self.db_manager.get_messages,
                channel_id,
                limit
            )
            
            return messages
            
        except Exception as e:
            self.logger.error(f"取得頻道上下文失敗: {e}")
            return []
    
    async def initialize_channel(self, channel_id: str, guild_id: str) -> bool:
        """初始化頻道記憶
        
        Args:
            channel_id: 頻道 ID
            guild_id: 伺服器 ID
            
        Returns:
            bool: 是否成功初始化
        """
        if not self._check_initialized():
            return False
        
        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                self.db_manager.create_channel,
                channel_id,
                guild_id,
                self.current_profile.vector_enabled,
                self.current_profile.name
            )
            
            if success and self.vector_manager:
                # 同時建立向量索引
                await loop.run_in_executor(
                    None,
                    self.vector_manager.create_channel_index,
                    channel_id
                )
            
            if success:
                self.logger.info(f"頻道記憶初始化完成: {channel_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"頻道記憶初始化失敗: {e}")
            return False
    
    async def get_stats(self) -> MemoryStats:
        """取得記憶系統統計資料
        
        Returns:
            MemoryStats: 統計資料
        """
        if not self._check_initialized():
            return MemoryStats(
                total_channels=0,
                total_messages=0,
                vector_enabled_channels=0,
                average_query_time_ms=0.0,
                cache_hit_rate=0.0,
                storage_size_mb=0.0
            )
        
        try:
            # 計算平均查詢時間
            avg_query_time = sum(self._query_times) / len(self._query_times) if self._query_times else 0.0
            
            # 計算快取命中率
            total_queries = self._cache_hits + self._cache_misses
            cache_hit_rate = self._cache_hits / total_queries if total_queries > 0 else 0.0
            
            # 從資料庫查詢統計資料
            total_channels = 0
            total_messages = 0
            vector_enabled_channels = 0
            storage_size_mb = 0.0
            
            if self.db_manager:
                try:
                    with self.db_manager.get_connection() as conn:
                        # 查詢頻道總數
                        try:
                            cursor = conn.execute("SELECT COUNT(*) FROM channels")
                            result = cursor.fetchone()
                            total_channels = result[0] if result else 0
                        except Exception as e:
                            self.logger.warning(f"無法查詢頻道總數: {e}")
                            total_channels = 0
                        
                        # 查詢訊息總數
                        try:
                            cursor = conn.execute("SELECT COUNT(*) FROM messages")
                            result = cursor.fetchone()
                            total_messages = result[0] if result else 0
                        except Exception as e:
                            self.logger.warning(f"無法查詢訊息總數: {e}")
                            total_messages = 0
                        
                        # 查詢啟用向量搜尋的頻道數（有嵌入資料的頻道）
                        try:
                            cursor = conn.execute("SELECT COUNT(DISTINCT channel_id) FROM embeddings")
                            result = cursor.fetchone()
                            vector_enabled_channels = result[0] if result else 0
                        except Exception as e:
                            self.logger.warning(f"無法查詢向量啟用頻道數: {e}")
                            vector_enabled_channels = 0
                        
                        # 計算資料庫檔案大小
                        try:
                            if self.db_manager.db_path.exists():
                                storage_size_mb = self.db_manager.db_path.stat().st_size / (1024 * 1024)
                        except Exception as e:
                            self.logger.warning(f"無法計算資料庫檔案大小: {e}")
                            storage_size_mb = 0.0
                except Exception as e:
                    self.logger.error(f"資料庫連接失敗: {e}")
                    # 保持預設值 0
            
            return MemoryStats(
                total_channels=total_channels,
                total_messages=total_messages,
                vector_enabled_channels=vector_enabled_channels,
                average_query_time_ms=avg_query_time,
                cache_hit_rate=cache_hit_rate,
                storage_size_mb=storage_size_mb
            )
            
        except Exception as e:
            self.logger.error(f"取得統計資料失敗: {e}")
            return MemoryStats(0, 0, 0, 0.0, 0.0, 0.0)
    
    def _check_initialized(self) -> bool:
        """檢查是否已初始化
        
        Returns:
            bool: 是否已初始化且啟用
        """
        if not self._initialized or not self._enabled:
            if not self._initialized:
                self.logger.warning("記憶系統尚未初始化")
            else:
                self.logger.debug("記憶系統已停用")
            return False
        return True
    
    async def cleanup(self) -> None:
        """清理資源"""
        try:
            loop = asyncio.get_event_loop()
            
            # 在清理前先儲存所有索引檔案
            if self.vector_manager:
                try:
                    self.logger.info("正在儲存所有向量索引檔案...")
                    save_results = await loop.run_in_executor(
                        None,
                        self.vector_manager.save_all_indices
                    )
                    success_count = sum(save_results.values())
                    total_count = len(save_results)
                    self.logger.info(f"索引檔案儲存完成: {success_count}/{total_count} 個成功")
                except Exception as e:
                    self.logger.error(f"儲存索引檔案失敗: {e}")
            
            if self.db_manager:
                await loop.run_in_executor(None, self.db_manager.close_connections)
            
            # 清理向量組件
            if self.embedding_service:
                await loop.run_in_executor(None, self.embedding_service.clear_cache)
            
            if self.vector_manager:
                await loop.run_in_executor(None, self.vector_manager.clear_cache)
            
            if self.search_engine:
                await loop.run_in_executor(None, self.search_engine.clear_cache)
            
            self.logger.info("記憶系統資源清理完成")
            
        except Exception as e:
            self.logger.error(f"清理記憶系統資源失敗: {e}")
    
    @property
    def is_enabled(self) -> bool:
        """記憶系統是否啟用"""
        return self._enabled and self._initialized
    
    @property
    def vector_enabled(self) -> bool:
        """向量搜尋是否啟用"""
        return (self.current_profile and
                self.current_profile.vector_enabled and
                self.is_enabled)
    
    async def store_message_from_dict(self, message_data: Dict[str, Any]) -> bool:
        """從字典資料儲存訊息（用於資料轉移）
        
        Args:
            message_data: 標準化的訊息資料字典
            
        Returns:
            bool: 是否成功儲存
        """
        try:
            # 確保必要欄位存在
            required_fields = ["message_id", "channel_id", "user_id", "content", "timestamp"]
            for field in required_fields:
                if field not in message_data:
                    raise ValueError(f"缺少必要欄位: {field}")
            
            # 轉換時間戳記格式
            timestamp = message_data["timestamp"]
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            elif not isinstance(timestamp, datetime):
                timestamp = datetime.now()
            
            # 準備訊息資料
            metadata = message_data.get("metadata")
            if metadata and isinstance(metadata, dict):
                metadata = json.dumps(metadata, ensure_ascii=False)
            elif metadata and not isinstance(metadata, str):
                metadata = str(metadata)
            
            processed_data = {
                "message_id": str(message_data["message_id"]),
                "channel_id": str(message_data["channel_id"]),
                "user_id": str(message_data["user_id"]),
                "content": str(message_data["content"]),
                "timestamp": timestamp,
                "message_type": message_data.get("message_type", "user"),
                "content_processed": message_data.get("content_processed"),
                "metadata": metadata
            }
            
            # 儲存到資料庫
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                self._store_message_sync,
                processed_data
            )
            
            if success and self.vector_enabled:
                # 非同步儲存向量嵌入
                asyncio.create_task(self._store_message_vector(processed_data))
            
            return success
            
        except Exception as e:
            self.logger.error(f"從字典儲存訊息失敗: {e}")
            return False
    
    async def clear_channel_memory(self, channel_id: str) -> bool:
        """清除頻道記憶
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            bool: 是否成功清除
        """
        if not self._check_initialized():
            return False
        
        try:
            loop = asyncio.get_event_loop()
            
            # 清除資料庫記錄
            success = await loop.run_in_executor(
                None,
                self._clear_channel_database,
                channel_id
            )
            
            if success and self.vector_manager:
                # 清除向量索引
                await loop.run_in_executor(
                    None,
                    self.vector_manager.delete_channel_index,
                    channel_id
                )
            
            if success:
                self.logger.info(f"頻道記憶已清除: {channel_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"清除頻道記憶失敗: {e}")
            return False
    
    def _clear_channel_database(self, channel_id: str) -> bool:
        """清除頻道的資料庫記錄
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            bool: 是否成功清除
        """
        try:
            with self.db_manager.get_connection() as conn:
                # 由於外鍵約束，刪除頻道會級聯刪除相關的訊息和嵌入
                conn.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
                conn.commit()
            
            return True
            
        except Exception as e:
            self.logger.error(f"清除頻道資料庫記錄失敗: {e}")
            return False
    