"""記憶系統核心管理器

實作 Discord 頻道記憶系統的核心功能，包括記憶存儲、檢索和管理。
提供統一的 API 接口供 Discord bot 使用。
"""

import asyncio
import json
import logging
import time
import uuid
from collections import OrderedDict
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
from .search_engine import SearchEngine, SearchQuery, SearchResult, SearchType, TimeRange, SearchCache
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
from .reranker_service import RerankerService
from .startup_logger import get_startup_logger, StartupLoggerManager


class RLock:
    """A re-entrant lock for asyncio, compatible with older Python versions."""
    def __init__(self):
        self._lock = asyncio.Lock()
        self._owner = None
        self._count = 0

    async def acquire(self):
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
            
        if self._owner is current_task:
            self._count += 1
            return
        await self._lock.acquire()
        self._owner = current_task
        self._count = 1

    async def release(self):
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None

        if self._owner is not current_task:
            return

        self._count -= 1
        if self._count == 0:
            self._owner = None
            self._lock.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.release()


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
    MAX_LOADED_INDICES = 50  # LRU 快取中最大載入索引數量
    
    def __init__(self, bot, config_path: Optional[str] = None):
        """初始化記憶管理器
        
        Args:
            bot: Discord bot 實例
            config_path: 配置檔案路徑
        """
        self.bot = bot
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
        self.reranker_service: Optional[RerankerService] = None
        self.vector_manager: Optional[VectorManager] = None
        self.search_engine: Optional[SearchEngine] = None
        
        # 文本分割組件
        self.segmentation_service: Optional[TextSegmentationService] = None
        self.segmentation_config: Optional[SegmentationConfig] = None
        
        # 性能統計與快取
        self._query_times: List[float] = []
        self._cache_hits = 0
        self._cache_misses = 0
        self.search_cache: Optional[SearchCache] = None
        
        # 索引管理 (延遲載入與 LRU)
        self.indices_status: Dict[str, str] = {}  # "on_disk" or "loaded"
        self.loaded_indices: OrderedDict[str, Any] = OrderedDict()
        
        # 執行緒安全鎖 (使用自訂的 RLock 避免死鎖)
        self._lock = RLock()
    
    async def find_and_remove_orphan_vectors(self) -> None:
        """
        查找並刪除孤立的向量。

        此方法負責識別和清理向量資料庫中不再具有對應訊息的向量嵌入。
        如果訊息被刪除或系統未正常關閉，就可能發生這種情況。
        """
        if not self.vector_manager or not self.db_manager:
            self.logger.warning("VectorManager 或 DatabaseManager 未初始化。跳過孤兒向量清理。")
            return

        self.logger.info("開始孤兒向量清理...")
        try:
            # 注意：這是一個佔位符實作。
            # 實際的邏輯需要根據您的 VectorManager 和 DatabaseManager 的 API 來實現。
            # 例如：
            # all_vector_ids = await asyncio.to_thread(self.vector_manager.get_all_vector_ids)
            # all_message_ids = await asyncio.to_thread(self.db_manager.get_all_message_ids)
            # orphan_ids = set(all_vector_ids) - set(all_message_ids)
            # if orphan_ids:
            #     self.logger.info(f"找到 {len(orphan_ids)} 個孤兒向量。正在刪除...")
            #     await self.vector_manager.remove_vectors_by_ids(list(orphan_ids))
            
            self.logger.info("孤兒向量清理任務已觸發（目前為佔位符）。")
            await asyncio.sleep(1) # 模擬非同步操作
            self.logger.info("孤兒向量清理完成。")

        except Exception as e:
            self.logger.error(f"孤兒向量清理期間發生錯誤: {e}", exc_info=True)

    async def cleanup_orphan_segments(self) -> Dict[str, int]:
        """
        查找並刪除所有孤兒片段（在向量索引中存在但在資料庫中沒有對應記錄的片段）。
        
        Returns:
            Dict[str, int]: {channel_id: removed_count}
        """
        if not self.vector_manager or not self.db_manager:
            self.logger.warning("VectorManager 或 DatabaseManager 未初始化，跳過孤兒片段清理。")
            return {}

        self.logger.info("開始孤兒片段清理...")
        removed_stats = {}
        try:
            # 步驟 1: 獲取所有向量索引中的 segment ID，按頻道分組
            all_vector_segments_by_channel = self.vector_manager.get_all_segment_ids_by_channel()

            # 步驟 2: 獲取資料庫中所有有效的 segment ID，按頻道分組
            all_db_segments_by_channel = await asyncio.to_thread(
                self.db_manager.get_all_segment_ids_by_channel
            )

            # 步驟 3: 遍歷每個頻道，找出孤兒
            all_channels = set(all_vector_segments_by_channel.keys()) | set(all_db_segments_by_channel.keys())
            
            for channel_id in all_channels:
                vector_ids = set(all_vector_segments_by_channel.get(channel_id, []))
                db_ids = set(all_db_segments_by_channel.get(channel_id, []))
                
                orphan_ids = list(vector_ids - db_ids)
                
                if orphan_ids:
                    self.logger.info(f"在頻道 {channel_id} 中找到 {len(orphan_ids)} 個孤兒片段。")
                    try:
                        removed_count = self.vector_manager.remove_vectors(channel_id, orphan_ids)
                        if removed_count > 0:
                            removed_stats[channel_id] = removed_count
                            self.logger.info(f"成功從頻道 {channel_id} 移除了 {removed_count} 個孤兒片段。")
                    except Exception as e:
                        self.logger.error(f"從頻道 {channel_id} 移除孤兒片段時發生錯誤: {e}")

            total_removed = sum(removed_stats.values())
            if total_removed > 0:
                self.logger.info(f"孤兒片段清理完成，共移除了 {total_removed} 個片段。")
            else:
                self.logger.info("未找到需要清理的孤兒片段。")

            return removed_stats

        except Exception as e:
            self.logger.error(f"孤兒片段清理期間發生錯誤: {e}", exc_info=True)
            return removed_stats

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
            
            # 初始化搜尋快取
            if memory_config.get("cache", {}).get("enabled", True):
                cache_config = memory_config.get("cache", {})
                self.search_cache = SearchCache(
                    max_size=cache_config.get("max_size", 1000),
                    ttl_seconds=cache_config.get("ttl_seconds", 3600)
                )
                self.logger.info("搜尋快取已啟用")
            else:
                self.search_cache = None
                self.logger.info("搜尋快取已停用")

            # 初始化重排序服務
            self.reranker_service = None
            if memory_config.get("reranker", {}).get("enabled", True):
                try:
                    # 直接實例化 RerankerService
                    self.reranker_service = await loop.run_in_executor(
                        None,
                        RerankerService,
                        self.current_profile
                    )
                    if self.reranker_service:
                        self.logger.info("重排序服務初始化成功")
                except Exception as e:
                    self.logger.warning(f"重排序服務初始化失敗: {e}")
                    get_startup_logger().log_warning(f"重排序服務初始化失敗: {e}")
                    self.reranker_service = None # 確保失敗時為 None

            # 初始化搜尋引擎
            self.search_engine = await loop.run_in_executor(
                None,
                SearchEngine,
                self.current_profile,
                self.embedding_service,
                self.vector_manager,
                self.db_manager,
                self.bot,
                self.reranker_service,
                self.search_cache,
                memory_config.get("reranker", {}).get("enabled", True)
            )
            
            # 預熱嵌入模型
            await loop.run_in_executor(None, self.embedding_service.warmup)
            
            # 預熱重排序模型
            if hasattr(self.search_engine, 'warmup_reranker'):
                await loop.run_in_executor(None, self.search_engine.warmup_reranker)
            
            # 掃描現有的索引檔案
            await self._load_existing_indices()

            # 在啟動時執行孤兒片段清理
            asyncio.create_task(self.cleanup_orphan_segments())
            
            self.logger.info("向量搜尋組件初始化完成")
            
        except Exception as e:
            self.logger.error(f"初始化向量組件失敗: {e}")
            # 不拋出例外，允許系統在無向量功能的情況下運行
            self.current_profile.vector_enabled = False
    
    async def _load_existing_indices(self) -> None:
        """掃描現有的索引檔案並記錄其狀態，但不立即載入。"""
        try:
            if not self.vector_manager or not self.current_profile.vector_enabled:
                return

            indices_path = self.vector_manager.storage_path
            if not indices_path.exists():
                self.logger.info("索引目錄不存在，跳過掃描現有索引")
                return

            index_files = list(indices_path.glob("*.index"))
            total_files = len(index_files)

            if total_files == 0:
                self.logger.info("沒有找到現有的索引檔案")
                return

            self.logger.info(f"找到 {total_files} 個現有索引檔案，將其標記為 'on_disk'")

            for index_file in index_files:
                channel_id = index_file.stem
                self.indices_status[channel_id] = "on_disk"

            self.logger.info(f"索引狀態初始化完成，共 {len(self.indices_status)} 個索引待命。")

        except Exception as e:
            self.logger.error(f"掃描現有索引時發生未預期的錯誤: {e}")
    
    async def _ensure_index_loaded(self, channel_id: str) -> None:
        """確保指定頻道的索引已載入記憶體，並管理 LRU 快取。"""
        if not self.vector_manager or not self.current_profile.vector_enabled:
            return

        async with self._lock:
            status = self.indices_status.get(channel_id)

            if status == "loaded":
                if channel_id in self.loaded_indices:
                    self.loaded_indices.move_to_end(channel_id)
                    self.logger.debug(f"索引 {channel_id} 已載入，更新其為最近使用。")
                return

            if status == "on_disk":
                self.logger.info(f"索引 {channel_id} 狀態為 'on_disk'，開始載入...")

                # LRU 快取管理：檢查是否達到上限
                if len(self.loaded_indices) >= self.MAX_LOADED_INDICES:
                    lru_channel_id, _ = self.loaded_indices.popitem(last=False)
                    self.indices_status[lru_channel_id] = "on_disk"
                    # 使用新加入的 unload_channel_index 方法
                    if not self.vector_manager.unload_channel_index(lru_channel_id):
                        self.logger.error(f"卸載索引 {lru_channel_id} 失敗")
                    else:
                        self.logger.info(f"LRU 快取已滿，卸載最久未使用的索引: {lru_channel_id}")

                # 載入新索引
                loop = asyncio.get_event_loop()
                try:
                    success = await loop.run_in_executor(
                        None,
                        self.vector_manager.create_channel_index,
                        channel_id
                    )
                    if success:
                        self.indices_status[channel_id] = "loaded"
                        index_instance = self.vector_manager.get_channel_index(channel_id)
                        if index_instance:
                            self.loaded_indices[channel_id] = index_instance
                            self.logger.info(f"成功載入索引: {channel_id}")
                        else:
                             self.logger.error(f"載入索引 {channel_id} 後無法獲取實例")
                             self.indices_status[channel_id] = "on_disk"
                    else:
                        self.logger.error(f"載入索引 {channel_id} 失敗")
                        self.indices_status.pop(channel_id, None)
                except Exception as e:
                    self.logger.error(f"載入索引 {channel_id} 時發生嚴重錯誤: {e}")
                    self.indices_status.pop(channel_id, None)
                    raise MemorySystemError(f"無法載入頻道 {channel_id} 的索引: {e}")

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
        if not self.embedding_service or not self.vector_manager:
            return

        try:
            content_to_embed = message_data.get("content_processed")
            if not content_to_embed or not content_to_embed.strip():
                self.logger.debug(f"訊息 {message_data['message_id']} 內容為空，跳過向量化")
                return

            channel_id = message_data['channel_id']
            message_id = message_data['message_id']

            # 確保索引已載入
            await self._ensure_index_loaded(channel_id)

            # 在執行緒池中執行嵌入操作
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None, self.embedding_service.encode_text, content_to_embed
            )

            # 在主事件循環中新增向量到索引
            success = self.vector_manager.add_vectors(
                channel_id=channel_id,
                vectors=np.array([embedding]),
                ids=[message_id]
            )

            if success:
                # 將嵌入向量儲存到資料庫
                self._store_embedding_to_database(
                    message_id=message_id,
                    channel_id=channel_id,
                    embedding=embedding
                )
            else:
                self.logger.error(f"無法新增向量到索引 {channel_id} for message {message_id}")

        except Exception as e:
            self.logger.error(f"儲存訊息向量失敗: {e}", exc_info=True)
            raise VectorOperationError(f"儲存訊息向量失敗: {e}")
    
    async def _process_message_segmentation(self, message_data: Dict[str, Any]) -> None:
        """處理訊息的文本分割

        Args:
            message_data: 訊息資料
        """
        if not self.segmentation_service:
            return

        try:
            channel_id = message_data['channel_id']
            
            if self.segmentation_config.async_processing:
                # 非同步處理
                asyncio.create_task(self._process_segmentation_async(channel_id))
            else:
                # 同步處理
                completed_segment = self.segmentation_service.process_message(message_data)
                if completed_segment:
                    await self._post_process_completed_segment(completed_segment)
                    
        except Exception as e:
            self.logger.error(f"處理訊息分割失敗: {e}")
    
    async def _process_segmentation_async(
        self, 
        channel_id: str, 
        force_segment: bool = False, 
        force_all: bool = False
    ) -> None:
        """非同步處理分割邏輯

        Args:
            channel_id: 頻道 ID
            force_segment: 是否強制分割
            force_all: 是否處理所有待處理訊息
        """
        if not self.segmentation_service:
            return

        try:
            self.logger.info(f"開始對頻道 {channel_id} 進行批次文本分割...")
            
            # 1. 從資料庫獲取所有訊息
            loop = asyncio.get_event_loop()
            messages = await loop.run_in_executor(
                None,
                self.db_manager.get_messages,
                str(channel_id),  # 確保 channel_id 是字串
                None  # limit
            )
            
            if not messages:
                self.logger.info(f"頻道 {channel_id} 中沒有需要處理的訊息。")
                return
            
            # 2. 按時間戳排序
            messages.sort(key=lambda m: datetime.fromisoformat(m['timestamp']))
            
            self.logger.info(f"找到 {len(messages)} 條訊息，開始處理...")
            
            processed_count = 0
            # 3. 遍歷並處理每條訊息
            for message_data in messages:
                try:
                    # 4. 呼叫單一訊息處理方法
                    completed_segment = await self.segmentation_service.process_new_message(
                        message_id=message_data['message_id'],
                        channel_id=message_data['channel_id'],
                        content=message_data['content'],
                        timestamp=datetime.fromisoformat(message_data['timestamp']),
                        user_id=message_data['user_id']
                    )
                    
                    # 5. 後處理已完成的片段
                    if completed_segment:
                        await self._post_process_completed_segment(completed_segment)
                    
                    processed_count += 1
                except Exception as inner_e:
                    self.logger.error(f"處理訊息 {message_data['message_id']} 分割時出錯: {inner_e}")

            self.logger.info(f"頻道 {channel_id} 的批次分割完成，共處理 {processed_count} 條訊息。")

        except Exception as e:
            self.logger.error(f"非同步處理頻道 {channel_id} 分割失敗: {e}")
    
    async def _post_process_completed_segment(self, segment) -> None:
        """後處理已完成的片段

        Args:
            segment: 已完成的片段物件
        """
        try:
            if self.current_profile.vector_enabled:
                await self._add_segment_to_vector_index(segment)
        except Exception as e:
            self.logger.error(f"後處理片段 {segment.id} 失敗: {e}")
    
    async def _add_segment_to_vector_index(self, segment) -> None:
        """將片段添加到向量索引

        Args:
            segment: 片段物件
        """
        if not self.embedding_service or not self.vector_manager:
            return

        try:
            # 確保索引已載入
            await self._ensure_index_loaded(segment.channel_id)

            # 在執行緒池中執行
            loop = asyncio.get_event_loop()
            
            def embed_and_add_sync():
                try:
                    embedding = self.embedding_service.encode_text(segment.segment_summary)
                    self.vector_manager.add_vectors(
                        channel_id=segment.channel_id,
                        vectors=np.array([embedding]),
                        ids=[segment.segment_id]
                    )
                except Exception as e:
                    self.logger.error(f"處理片段向量時發生錯誤: {e}")
                    raise

            await loop.run_in_executor(None, embed_and_add_sync)
            
        except Exception as e:
            self.logger.error(f"新增片段到向量索引失敗: {e}")
    
    def _store_embedding_to_database(
        self, 
        message_id: str, 
        channel_id: str, 
        embedding: np.ndarray
    ) -> bool:
        """將嵌入向量儲存到資料庫

        Args:
            message_id: 訊息 ID
            channel_id: 頻道 ID
            embedding: 嵌入向量

        Returns:
            bool: 是否成功儲存
        """
        if not self.db_manager or not self.embedding_service:
            return False

        try:
            vector_data = embedding.tobytes()
            model_version = self.embedding_service.get_model_version()
            dimension = embedding.shape[0]

            with self.db_manager.get_connection() as conn:
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
            except Exception as disk_e:
                self.logger.error(f"檢查磁盤空間失敗: {disk_e}")
            
            self.logger.info(f"頻道 {channel_id} 索引儲存診斷完成")
            
        except Exception as e:
            self.logger.error(f"診斷索引儲存問題時發生錯誤: {e}")
    
    async def search_memory(self, search_query: SearchQuery) -> 'SearchResult':
        """搜尋相關記憶（包裝器方法）

        Args:
            search_query: 搜尋查詢物件

        Returns:
            SearchResult: 搜尋結果
        """
        if not self._check_initialized() or not self.search_engine:
            raise MemorySystemError("記憶系統未初始化或搜尋引擎不可用")

        try:
            start_time = time.time()

            # 步驟 1: 檢查快取
            cache_key = None
            if self.search_cache:
                cache_key = search_query.get_cache_key()
                cached_result = self.search_cache.get(cache_key)
                if cached_result:
                    self._cache_hits += 1
                    total_time_ms = (time.time() - start_time) * 1000
                    cached_result.search_time_ms = total_time_ms
                    cached_result.cache_hit = True
                    self.logger.info(
                        f"記憶搜尋完成 (快取命中) - "
                        f"頻道: {search_query.channel_id}, "
                        f"耗時: {total_time_ms:.2f}ms"
                    )
                    # 即使快取命中，也要更新 LRU 順序
                    if search_query.search_type in [SearchType.SEMANTIC, SearchType.HYBRID]:
                        await self._ensure_index_loaded(search_query.channel_id)
                    return cached_result
            
            self._cache_misses += 1

            # 步驟 2: 延遲載入索引 (如果需要)
            if search_query.search_type in [SearchType.SEMANTIC, SearchType.HYBRID]:
                await self._ensure_index_loaded(search_query.channel_id)

            # 步驟 3: 執行搜尋
            result = await self.search_engine.search(search_query)
            
            # 步驟 4: 更新統計數據
            total_time_ms = (time.time() - start_time) * 1000
            self._query_times.append(total_time_ms)
            result.search_time_ms = total_time_ms
            result.cache_hit = False

            # 步驟 5: 存入快取
            if self.search_cache and cache_key:
                self.search_cache.put(cache_key, result)

            self.logger.info(
                f"記憶搜尋完成 - "
                f"頻道: {search_query.channel_id}, "
                f"類型: {result.search_method}, "
                f"找到: {len(result.messages)}/{result.total_found}, "
                f"耗時: {total_time_ms:.2f}ms, "
                f"快取命中: False"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"記憶搜尋失敗: {e}")
            raise SearchError(f"記憶搜尋失敗: {e}")
    
    async def cleanup(self) -> None:
        """清理記憶體資源和快取（使用 tqdm 進度條）"""
        try:
            self.logger.info("開始記憶體系統清理...")
            
            cleanup_tasks = []
            
            # 清理搜尋引擎
            if self.search_engine:
                cleanup_tasks.append(("搜尋引擎", self.search_engine.cleanup))
            
            # 清理向量管理器
            if self.vector_manager:
                cleanup_tasks.append(("向量管理器", self.vector_manager.cleanup))
            
            # 清理資料庫管理器
            if self.db_manager:
                cleanup_tasks.append(("資料庫管理器", self.db_manager.close_connections))
            
            # 使用 tqdm 顯示進度
            with tqdm.tqdm(total=len(cleanup_tasks), desc="清理記憶體資源", unit="task") as pbar:
                for name, cleanup_func in cleanup_tasks:
                    try:
                        if asyncio.iscoroutinefunction(cleanup_func):
                            await cleanup_func()
                        else:
                            cleanup_func()
                        self.logger.debug(f"{name} 清理完成")
                    except Exception as e:
                        self.logger.error(f"{name} 清理失敗: {e}")
                    finally:
                        pbar.update(1)
            
            # 清理 GPU 記憶體
            if self.vector_manager and self.vector_manager.gpu_memory_manager:
                try:
                    self.vector_manager.gpu_memory_manager.clear_gpu_memory()
                    self.logger.debug("GPU 記憶體清理完成")
                except Exception as e:
                    self.logger.error(f"GPU 記憶體清理失敗: {e}")
            
            self._initialized = False
            self.logger.info("記憶體系統清理完成")
            
        except Exception as e:
            self.logger.error(f"記憶體清理時發生嚴重錯誤: {e}")