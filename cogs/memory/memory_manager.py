"""記憶系統核心管理器

實作 Discord 頻道記憶系統的核心功能，包括記憶存儲、檢索和管理。
提供統一的 API 接口供 Discord bot 使用。
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import discord
import numpy as np
import tqdm

from .database import DatabaseManager
from .config import MemoryConfig, MemoryProfile
from .embedding_service import EmbeddingService, embedding_service_manager
from .vector_manager import VectorManager
from .search_engine import SearchEngine, SearchQuery, SearchResult, SearchType, TimeRange
from .segmentation_service import (
    TextSegmentationService,
    SegmentationConfig,
    SegmentationStrategy,
    initialize_segmentation_service
)
from .exceptions import (
    MemorySystemError,
    DatabaseError,
    ConfigurationError,
    SearchError,
    VectorOperationError
)
from .startup_logger import get_startup_logger, StartupLoggerManager


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
    
    INDEX_LOAD_CONCURRENCY_THRESHOLD = 10  # 載入索引時，觸發並行處理的檔案數量閾值
    
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
        
        # 文本分割組件
        self.segmentation_service: Optional[TextSegmentationService] = None
        self.segmentation_config: Optional[SegmentationConfig] = None
        
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
            # 初始化啟動日誌管理器
            startup_logger = StartupLoggerManager.get_instance(self.logger)
            if startup_logger:
                startup_logger.start_startup_phase()
            
            self.logger.info("開始初始化記憶系統...")
            
            # 載入配置
            await self._load_configuration()
            
            # 檢查是否啟用記憶系統
            memory_config = self.config.get_memory_config()
            self._enabled = memory_config.get("enabled", True)
            
            if not self._enabled:
                self.logger.info("記憶系統已停用")
                if startup_logger:
                    startup_logger.end_startup_phase()
                return False
            
            # 初始化資料庫
            await self._initialize_database()
            
            # 載入配置檔案
            self.current_profile = self.config.get_current_profile()
            
            # 初始化向量組件
            await self._initialize_vector_components()
            
            # 初始化分割服務
            await self._initialize_segmentation_service()
            
            self._initialized = True
            
            # 結束啟動階段並輸出摘要
            if startup_logger:
                startup_logger.end_startup_phase()
            
            self.logger.info(f"記憶系統初始化完成 (配置檔案: {self.current_profile.name})")
            
            return True
            
        except Exception as e:
            # 確保啟動階段結束
            startup_logger = get_startup_logger()
            if startup_logger:
                startup_logger.log_error(f"記憶系統初始化失敗: {e}")
                startup_logger.end_startup_phase()
            
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
                memory_config.get("cache", {}).get("enabled", True),
                memory_config.get("reranker", {}).get("enabled", True)  # 預設啟用重排序
            )
            
            # 預熱嵌入模型
            await loop.run_in_executor(None, self.embedding_service.warmup)
            
            # 預熱重排序模型
            if hasattr(self.search_engine, 'warmup_reranker'):
                await loop.run_in_executor(None, self.search_engine.warmup_reranker)
            
            # 載入現有的索引檔案
            await self._load_existing_indices()
            
            self.logger.info("向量搜尋組件初始化完成")
            
        except Exception as e:
            self.logger.error(f"初始化向量組件失敗: {e}")
            # 不拋出例外，允許系統在無向量功能的情況下運行
            self.current_profile.vector_enabled = False
    
    async def _load_existing_indices(self) -> None:
        """以非阻塞方式逐一載入所有現有的索引檔案到記憶體中。"""
        try:
            if not self.vector_manager or not self.current_profile.vector_enabled:
                return

            indices_path = self.vector_manager.storage_path
            if not indices_path.exists():
                self.logger.info("索引目錄不存在，跳過載入現有索引")
                return

            index_files = list(indices_path.glob("*.index"))
            total_files = len(index_files)

            if total_files == 0:
                self.logger.info("沒有找到現有的索引檔案")
                return

            self.logger.info(f"找到 {total_files} 個現有索引檔案，開始非阻塞載入...")

            loaded_count = 0
            failed_count = 0

            # 根據檔案大小排序，優先載入較小的索引
            index_files_sorted = sorted(
                index_files,
                key=lambda f: f.stat().st_size if f.exists() else 0
            )

            loop = asyncio.get_event_loop()
            with tqdm.tqdm(total=total_files, desc="載入記憶體索引", unit="file") as pbar:
                for index_file in index_files_sorted:
                    try:
                        channel_id = index_file.stem
                        
                        # 在獨立的執行緒中執行阻塞的檔案 I/O 和反序列化操作
                        success = await loop.run_in_executor(
                            None,
                            self.vector_manager.create_channel_index,
                            channel_id
                        )
                        
                        if success:
                            self.logger.debug(f"成功載入頻道 {channel_id} 的索引")
                            loaded_count += 1
                        else:
                            self.logger.warning(f"載入頻道 {channel_id} 的索引失敗")
                            failed_count += 1
                            
                    except Exception as e:
                        self.logger.error(f"處理索引檔案 {index_file.name} 時發生嚴重錯誤: {e}")
                        failed_count += 1
                    finally:
                        # 確保無論成功或失敗，進度條都會更新
                        pbar.update(1)

            self.logger.info(
                f"索引載入完成: {loaded_count} 個成功，{failed_count} 個失敗，"
                f"總共 {total_files} 個索引檔案"
            )

            if self.vector_manager.gpu_memory_manager:
                self.vector_manager.gpu_memory_manager.log_memory_stats(force_log=True)
            
        except Exception as e:
            self.logger.error(f"載入現有索引時發生未預期的錯誤: {e}")
    
    async def _initialize_segmentation_service(self) -> None:
        """初始化文本分割服務"""
        try:
            # 載入分割配置
            segmentation_config_data = self.config.get_segmentation_config()
            
            # 建立分割配置物件
            self.segmentation_config = SegmentationConfig(
                enabled=segmentation_config_data.get("enabled", True),
                strategy=SegmentationStrategy(segmentation_config_data.get("strategy", "hybrid")),
                min_interval_minutes=segmentation_config_data.get("dynamic_interval", {}).get("min_minutes", 5),
                max_interval_minutes=segmentation_config_data.get("dynamic_interval", {}).get("max_minutes", 120),
                base_interval_minutes=segmentation_config_data.get("dynamic_interval", {}).get("base_minutes", 30),
                activity_multiplier=segmentation_config_data.get("dynamic_interval", {}).get("activity_multiplier", 0.2),
                similarity_threshold=segmentation_config_data.get("semantic_threshold", {}).get("similarity_cutoff", 0.6),
                min_messages_per_segment=segmentation_config_data.get("semantic_threshold", {}).get("min_messages_per_segment", 3),
                max_messages_per_segment=segmentation_config_data.get("semantic_threshold", {}).get("max_messages_per_segment", 50),
                batch_size=segmentation_config_data.get("processing", {}).get("batch_size", 20),
                async_processing=segmentation_config_data.get("processing", {}).get("async_processing", True),
                background_segmentation=segmentation_config_data.get("processing", {}).get("background_segmentation", True),
                coherence_threshold=segmentation_config_data.get("quality_control", {}).get("coherence_threshold", 0.5),
                merge_small_segments=segmentation_config_data.get("quality_control", {}).get("merge_small_segments", True),
                split_large_segments=segmentation_config_data.get("quality_control", {}).get("split_large_segments", True)
            )
            
            # 檢查是否啟用分割功能
            if not self.segmentation_config.enabled:
                self.logger.info("文本分割功能已停用")
                return
            
            # 檢查必要組件是否可用
            if not self.embedding_service:
                self.logger.warning("嵌入服務未初始化，停用文本分割功能")
                self.segmentation_config.enabled = False
                return
            
            # 初始化分割服務
            self.segmentation_service = initialize_segmentation_service(
                db_manager=self.db_manager,
                embedding_service=self.embedding_service,
                config=self.segmentation_config,
                profile=self.current_profile
            )
            
            self.logger.info(f"文本分割服務初始化完成 (策略: {self.segmentation_config.strategy.value})")
            
        except Exception as e:
            self.logger.error(f"初始化文本分割服務失敗: {e}")
            # 不拋出例外，允許系統在無分割功能的情況下運行
            if self.segmentation_config:
                self.segmentation_config.enabled = False
    
    async def get_stats(self) -> MemoryStats:
        """取得記憶系統統計資料
        
        Returns:
            MemoryStats: 記憶系統統計資料
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
            # 在執行緒池中執行統計查詢
            loop = asyncio.get_event_loop()
            
            # 取得基本統計
            total_channels = await loop.run_in_executor(
                None, self.db_manager.get_channel_count
            )
            
            total_messages = await loop.run_in_executor(
                None, self.db_manager.get_message_count
            )
            
            # 計算向量啟用的頻道數
            vector_enabled_channels = 0
            if self.vector_manager:
                memory_stats = self.vector_manager.get_memory_stats()
                vector_enabled_channels = memory_stats.get("total_indices", 0)
            
            # 計算平均查詢時間
            avg_query_time = (
                sum(self._query_times) / len(self._query_times)
                if self._query_times else 0.0
            )
            
            # 計算快取命中率
            total_queries = self._cache_hits + self._cache_misses
            cache_hit_rate = (
                self._cache_hits / total_queries * 100
                if total_queries > 0 else 0.0
            )
            
            # 計算儲存大小
            storage_size_mb = await loop.run_in_executor(
                None, self._calculate_storage_size
            )
            
            return MemoryStats(
                total_channels=total_channels,
                total_messages=total_messages,
                vector_enabled_channels=vector_enabled_channels,
                average_query_time_ms=avg_query_time,
                cache_hit_rate=cache_hit_rate,
                storage_size_mb=storage_size_mb
            )
            
        except Exception as e:
            self.logger.error(f"取得記憶統計失敗: {e}")
            return MemoryStats(
                total_channels=0,
                total_messages=0,
                vector_enabled_channels=0,
                average_query_time_ms=0.0,
                cache_hit_rate=0.0,
                storage_size_mb=0.0
            )
    
    def _calculate_storage_size(self) -> float:
        """計算儲存大小（MB）
        
        Returns:
            float: 儲存大小（MB）
        """
        try:
            total_size = 0
            
            # 計算資料庫大小
            if self.db_manager and hasattr(self.db_manager, 'db_path'):
                db_path = Path(self.db_manager.db_path)
                if db_path.exists():
                    total_size += db_path.stat().st_size
            
            # 計算索引檔案大小
            if self.vector_manager and hasattr(self.vector_manager, 'storage_path'):
                indices_path = self.vector_manager.storage_path
                if indices_path.exists():
                    for file_path in indices_path.rglob("*"):
                        if file_path.is_file():
                            total_size += file_path.stat().st_size
            
            return total_size / (1024 * 1024)  # 轉換為 MB
            
        except Exception as e:
            self.logger.warning(f"計算儲存大小失敗: {e}")
            return 0.0
    
    def _check_initialized(self) -> bool:
        """檢查是否已初始化
        
        Returns:
            bool: 是否已初始化
        """
        return self._initialized and self._enabled
    
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
                    
                    # 如果啟用分割功能，處理文本分割
                    if (self.segmentation_config and 
                        self.segmentation_config.enabled and 
                        self.segmentation_service):
                        await self._process_message_segmentation(message_data)
                    
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
                    # 確保索引目錄存在
                    await self._ensure_indices_directory()
                    
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
                            # 檢查具體的儲存問題
                            await self._diagnose_index_storage_issue(channel_id)
                except Exception as e:
                    self.logger.warning(f"定期儲存索引檔案失敗: {e}")
                    # 記錄詳細的錯誤資訊
                    await self._diagnose_index_storage_issue(channel_id, str(e))
            
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
    
    async def _process_message_segmentation(self, message_data: Dict[str, Any]) -> None:
        """處理訊息的文本分割
        
        Args:
            message_data: 訊息資料
        """
        try:
            # 檢查是否有有效的內容
            content = message_data.get("content_processed", "") or message_data.get("content", "")
            if not content.strip():
                return
            
            # 準備分割處理參數
            message_id = message_data["message_id"]
            channel_id = message_data["channel_id"]
            user_id = message_data["user_id"]
            timestamp = message_data["timestamp"]
            
            # 在背景執行分割處理
            if self.segmentation_config.background_segmentation:
                # 非同步處理，不等待結果
                asyncio.create_task(
                    self._process_segmentation_async(
                        message_id, channel_id, content, timestamp, user_id
                    )
                )
            else:
                # 同步處理
                await self._process_segmentation_async(
                    message_id, channel_id, content, timestamp, user_id
                )
                
        except Exception as e:
            self.logger.error(f"處理訊息分割失敗: {e}")
            # 不拋出例外，避免影響主要的訊息儲存流程
    
    async def _process_segmentation_async(
        self,
        message_id: str,
        channel_id: str,
        content: str,
        timestamp: datetime,
        user_id: str
    ) -> None:
        """非同步處理分割邏輯
        
        Args:
            message_id: 訊息 ID
            channel_id: 頻道 ID
            content: 訊息內容
            timestamp: 時間戳記
            user_id: 使用者 ID
        """
        try:
            # 呼叫分割服務處理新訊息
            completed_segment = await self.segmentation_service.process_new_message(
                message_id=message_id,
                channel_id=channel_id,
                content=content,
                timestamp=timestamp,
                user_id=user_id
            )
            
            if completed_segment:
                # 記錄完成的片段
                self.logger.debug(
                    f"完成對話片段: {completed_segment.segment_id}，"
                    f"訊息數: {completed_segment.message_count}，"
                    f"持續時間: {completed_segment.duration_minutes:.1f}分鐘"
                )
                
                # 可以在這裡添加額外的後處理邏輯
                await self._post_process_completed_segment(completed_segment)
                
        except Exception as e:
            self.logger.error(f"非同步分割處理失敗: {e}")
    
    async def _post_process_completed_segment(self, segment) -> None:
        """後處理已完成的片段
        
        Args:
            segment: 完成的對話片段
        """
        try:
            # 這裡可以添加額外的處理邏輯，例如：
            # 1. 更新向量索引
            # 2. 生成片段摘要
            # 3. 發送通知
            # 4. 更新統計資料
            
            # 更新片段的向量表示到向量索引（如果需要）
            if (segment.vector_representation is not None and 
                self.vector_manager and 
                self.current_profile.vector_enabled):
                
                # 將片段向量添加到特殊的片段索引中
                await self._add_segment_to_vector_index(segment)
            
        except Exception as e:
            self.logger.warning(f"後處理片段失敗: {e}")
    
    async def _add_segment_to_vector_index(self, segment) -> None:
        """將片段添加到向量索引
        
        Args:
            segment: 對話片段
        """
        try:
            if not segment.vector_representation.any():
                return
            
            # 使用特殊的索引鍵來標識片段向量
            segment_index_key = f"segments_{segment.channel_id}"
            
            # 在執行緒池中執行向量操作
            loop = asyncio.get_event_loop()
            
            # 確保片段索引存在
            await loop.run_in_executor(
                None,
                self.vector_manager.create_channel_index,
                segment_index_key
            )
            
            # 添加片段向量
            await loop.run_in_executor(
                None,
                self.vector_manager.add_vectors,
                segment_index_key,
                segment.vector_representation.reshape(1, -1),
                [segment.segment_id]
            )
            
            self.logger.debug(f"片段向量已添加到索引: {segment.segment_id}")
            
        except Exception as e:
            self.logger.warning(f"添加片段到向量索引失敗: {e}")
    
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
            # 序列化向量資料
            vector_data = embedding.tobytes()
            
            with self.db_manager.get_connection() as conn:
                # 適應現有資料庫結構：使用 id 作為主鍵（自動遞增）
                # 添加 user_id 欄位以符合現有結構
                conn.execute("""
                    INSERT INTO embeddings
                    (message_id, channel_id, user_id, vector_data,
                     model_version, dimension)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (message_id, channel_id, None, vector_data,
                      model_version, dimension))
                conn.commit()
            
            self.logger.debug(f"成功儲存嵌入向量到資料庫: message_id={message_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"儲存嵌入向量到資料庫失敗: {e}")
            return False
    
    def _check_initialized(self) -> bool:
        """檢查是否已初始化
        
        Returns:
            bool: 是否已初始化且啟用
        """
        if not self._initialized:
            self.logger.warning("記憶系統未初始化")
            return False
        
        if not self._enabled:
            self.logger.debug("記憶系統已停用")
            return False
        
        return True
    
    @property
    def is_enabled(self) -> bool:
        """記憶系統是否啟用
        
        Returns:
            bool: 是否啟用
        """
        return self._enabled and self._initialized
    
    async def _ensure_indices_directory(self) -> bool:
        """確保索引目錄存在並有寫入權限
        
        Returns:
            bool: 目錄是否可用
        """
        try:
            if not self.vector_manager:
                return False
            
            indices_path = self.vector_manager.storage_path
            
            # 創建目錄（如果不存在）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: indices_path.mkdir(parents=True, exist_ok=True)
            )
            
            # 檢查寫入權限
            test_file = indices_path / ".write_test"
            await loop.run_in_executor(None, test_file.touch)
            await loop.run_in_executor(None, test_file.unlink)
            
            return True
            
        except Exception as e:
            self.logger.error(f"確保索引目錄失敗: {e}")
            return False
    
    async def _diagnose_index_storage_issue(self, channel_id: str, error_msg: str = None) -> None:
        """診斷索引儲存問題
        
        Args:
            channel_id: 頻道 ID
            error_msg: 錯誤訊息（可選）
        """
        try:
            if not self.vector_manager:
                self.logger.error("向量管理器未初始化")
                return
            
            indices_path = self.vector_manager.storage_path
            
            # 檢查目錄是否存在
            if not indices_path.exists():
                self.logger.error(f"索引目錄不存在: {indices_path}")
                return
            
            # 檢查目錄權限
            if not indices_path.is_dir():
                self.logger.error(f"索引路徑不是目錄: {indices_path}")
                return
            
            # 檢查寫入權限
            try:
                test_file = indices_path / f".write_test_{channel_id}"
                test_file.touch()
                test_file.unlink()
                self.logger.debug(f"索引目錄寫入權限正常: {indices_path}")
            except Exception as perm_e:
                self.logger.error(f"索引目錄無寫入權限: {indices_path}, 錯誤: {perm_e}")
                return
            
            # 檢查索引是否存在於記憶體中
            with self.vector_manager._indices_lock:
                if channel_id not in self.vector_manager._indices:
                    self.logger.error(f"頻道 {channel_id} 的索引不在記憶體中")
                    return
            
            # 檢查磁盤空間
            try:
                import shutil
                total, used, free = shutil.disk_usage(indices_path)
                free_mb = free // (1024 * 1024)
                if free_mb < 100:  # 少於 100MB
                    self.logger.error(f"磁盤空間不足: 剩餘 {free_mb}MB")
                else:
                    self.logger.debug(f"磁盤空間足夠: 剩餘 {free_mb}MB")
            except Exception as disk_e:
                self.logger.warning(f"無法檢查磁盤空間: {disk_e}")
            
            # 記錄詳細錯誤
            if error_msg:
                self.logger.error(f"索引儲存失敗的具體錯誤: {error_msg}")
            else:
                self.logger.warning(f"頻道 {channel_id} 索引儲存失敗，但未提供具體錯誤訊息")
                
        except Exception as e:
            self.logger.error(f"診斷索引儲存問題時發生錯誤: {e}")

    async def search_memory(self, search_query) -> 'SearchResult':
        """搜尋相關記憶（包裝器方法）
        
        Args:
            search_query: 搜尋查詢物件
            
        Returns:
            SearchResult: 搜尋結果
            
        Raises:
            MemorySystemError: 當搜尋系統未初始化或搜尋失敗時
        """
        if not self._check_initialized():
            raise MemorySystemError("記憶系統未初始化或已停用")
        
        if not self.search_engine:
            raise MemorySystemError("搜尋引擎未初始化")
        
        try:
            start_time = time.time()
            
            # 在執行緒池中執行搜尋
            loop = asyncio.get_event_loop()
            search_result = await loop.run_in_executor(
                None,
                self.search_engine.search,
                search_query
            )
            
            # 記錄查詢時間統計
            query_time_ms = (time.time() - start_time) * 1000
            self._query_times.append(query_time_ms)
            
            # 限制統計資料大小
            if len(self._query_times) > 1000:
                self._query_times = self._query_times[-500:]
            
            # 更新快取統計
            if search_result.cache_hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1
            
            self.logger.debug(
                f"搜尋完成: 查詢時間 {query_time_ms:.1f}ms, "
                f"結果數量 {len(search_result.messages)}, "
                f"快取命中: {search_result.cache_hit}"
            )
            
            return search_result
            
        except Exception as e:
            self.logger.error(f"搜尋相關記憶時發生未預期錯誤: {e}")
            raise SearchError(f"搜尋相關記憶失敗: {e}")
    
    async def cleanup(self) -> None:
        """清理記憶體資源和快取（使用 tqdm 進度條）"""
        try:
            self.logger.info("開始記憶體系統清理...")
            loop = asyncio.get_event_loop()

            cleanup_tasks = []
            if hasattr(self, 'vector_manager') and self.vector_manager:
                cleanup_tasks.append(("向量管理器", lambda: loop.run_in_executor(None, self.vector_manager.cleanup)))
            if hasattr(self, 'search_engine') and self.search_engine:
                cleanup_tasks.append(("搜尋引擎", lambda: loop.run_in_executor(None, self.search_engine.cleanup)))
            if hasattr(self, 'embedding_service') and self.embedding_service:
                cleanup_tasks.append(("嵌入服務", lambda: loop.run_in_executor(None, self.embedding_service.cleanup)))
            if hasattr(self, 'segmentation_service') and self.segmentation_service and hasattr(self.segmentation_service, 'cleanup'):
                cleanup_tasks.append(("分割服務", lambda: loop.run_in_executor(None, self.segmentation_service.cleanup)))
            if hasattr(self, 'db_manager') and self.db_manager:
                db_cleanup = getattr(self.db_manager, 'close', getattr(self.db_manager, 'cleanup', None))
                if db_cleanup:
                    cleanup_tasks.append(("資料庫", lambda: loop.run_in_executor(None, db_cleanup)))

            with tqdm.tqdm(total=len(cleanup_tasks), desc="清理記憶體資源", unit="task") as pbar:
                for name, task in cleanup_tasks:
                    try:
                        pbar.set_postfix_str(name)
                        await task()
                        self.logger.debug(f"{name} 已清理")
                    except Exception as e:
                        self.logger.error(f"清理 {name} 時發生錯誤: {e}")
                    finally:
                        pbar.update(1)

            # 清理統計資料
            self._query_times.clear()
            self._cache_hits = 0
            self._cache_misses = 0

            # 強制垃圾回收
            import gc
            gc.collect()

            # 釋放 GPU 記憶體
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    self.logger.info("GPU 記憶體已清理")
            except ImportError:
                pass
            except Exception as e:
                self.logger.warning(f"清理 GPU 記憶體時發生錯誤: {e}")

            self._initialized = False
            self.logger.info("記憶體系統清理完成")
            
        except Exception as e:
            self.logger.error(f"記憶體清理時發生嚴重錯誤: {e}")
            # 即使發生錯誤也要嘗試強制清理
            try:
                import gc
                gc.collect()
                if hasattr(torch, 'cuda') and torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass