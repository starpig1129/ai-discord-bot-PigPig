"""記憶系統核心管理器

實作 Discord 頻道記憶系統的核心功能，包括記憶存儲、檢索和管理。
提供統一的 API 接口供 Discord bot 使用。
"""

import asyncio
import json
import logging
import time
import gc
import uuid
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum

import discord
import numpy as np
import tqdm
import function as func

from .database import DatabaseManager
from .config import MemoryConfig, MemoryProfile
from .embedding_service import EmbeddingService, embedding_service_manager
from .fallback_memory_manager import FallbackMemoryManager
from .vector_manager import get_vector_manager, VectorManager
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
        self.logger.info("MemoryManager __init__: 實例已創建。")
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
        
        # 備用記憶體管理器
        self.fallback_memory_manager: Optional[FallbackMemoryManager] = None
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
        
        # 背景任務追蹤（用於優雅關閉時取消）
        self._bg_tasks: Set[asyncio.Task] = set()
    
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
            await func.func.report_error(e, "Orphan vector cleanup")

    async def cleanup_orphan_segments(self) -> Dict[str, int]:
        """
        查找並刪除所有孤兒向量，包括片段和單一訊息向量。
        
        Returns:
            Dict[str, int]: {channel_id: removed_count}
        """
        self.logger.info("cleanup_orphan_segments: 函式開始執行。")
        if not self.vector_manager or not self.db_manager:
            self.logger.warning("VectorManager 或 DatabaseManager 未初始化，跳過孤兒向量清理。")
            return {}

        self.logger.info("開始全面的孤兒向量清理...")
        removed_stats = {}
        try:
            # 新增步驟：確保所有索引都已載入，以解決時序問題
            self.logger.info("cleanup_orphan_segments: 正在確保所有向量索引都已載入...")
            await self.vector_manager.load_all_indexes()
            self.logger.info("cleanup_orphan_segments: 所有索引載入完成。")

            # 步驟 1: 獲取所有向量 ID，按頻道分組
            all_vector_ids_by_channel = self.vector_manager.get_all_segment_ids_by_channel()
            vector_ids_count = sum(len(ids) for ids in all_vector_ids_by_channel.values())
            self.logger.info(f"cleanup_orphan_segments: 從向量資料庫獲取到 {vector_ids_count} 個 ID。")
            if vector_ids_count > 0:
                sample_ids = next(iter(all_vector_ids_by_channel.values()), [])[:5]
                self.logger.info(f"cleanup_orphan_segments: 向量 ID 範例: {sample_ids}")

            # 步驟 2: 獲取所有資料庫中的有效 ID
            all_db_segment_ids = await asyncio.to_thread(self.db_manager.get_all_segment_ids)
            self.logger.info(f"cleanup_orphan_segments: 從 db_manager.get_all_segment_ids() 獲取到 {len(all_db_segment_ids)} 個片段 ID。")
            
            all_db_message_ids = await asyncio.to_thread(self.db_manager.get_all_message_ids)
            self.logger.info(f"cleanup_orphan_segments: 從 db_manager.get_all_message_ids() 獲取到 {len(all_db_message_ids)} 個訊息 ID。")
            
            # 將 ID 轉換為字串集合以便快速查找
            valid_segment_ids = {f"seg_{sid}" for sid in all_db_segment_ids}
            valid_message_ids = {f"msg_{mid}" for mid in all_db_message_ids}
            valid_legacy_message_ids = {str(mid) for mid in all_db_message_ids}

            # 步驟 3: 遍歷每個頻道，採用強韌格式驗證與延後批次刪除
            VALID_ID_RE = re.compile(r'^(?:msg_(\d+)|seg_(\d+)|dialogue_history_[A-Za-z0-9_\-]+|legacy_[A-Za-z0-9_\-]+|\d+)$')
            DIALOG_TWO_NUM_RE = re.compile(r'^dialogue_history_(\d+)_(\d+)$')
            candidate_deletions: Dict[str, List[str]] = {}

            for channel_id, vector_ids in all_vector_ids_by_channel.items():
                orphan_ids: List[str] = []
                for vec_id in vector_ids:
                    is_orphan = False

                    # 先用統一正則判斷是否為已知合法格式
                    if not VALID_ID_RE.match(vec_id):
                        # 未知格式一律視為潛在孤兒（安全起見）
                        self.logger.warning(f"cleanup_orphan_segments: 頻道 {channel_id} 發現未知格式向量 ID，將標記刪除: {vec_id}")
                        is_orphan = True
                    else:
                        # 已知格式再依型別執行嚴謹驗證
                        if vec_id.startswith('seg_'):
                            if vec_id not in valid_segment_ids:
                                is_orphan = True
                        elif vec_id.startswith('msg_'):
                            if vec_id not in valid_message_ids:
                                is_orphan = True
                        elif vec_id.isdigit():
                            if vec_id not in valid_legacy_message_ids:
                                is_orphan = True
                        elif vec_id.startswith('dialogue_history_'):
                            # 嘗試解析兩段數字舊版格式：dialogue_history_{thread_id}_{message_id}
                            m2 = DIALOG_TWO_NUM_RE.match(vec_id)
                            if m2:
                                legacy_msg_id = m2.group(2)
                                if (f"msg_{legacy_msg_id}" in valid_message_ids) or (legacy_msg_id in valid_legacy_message_ids):
                                    is_orphan = False
                                else:
                                    is_orphan = True
                            else:
                                # 其他 dialogue_history_* 視為合法格式但不強制解析，保留避免誤刪
                                self.logger.debug(f"cleanup_orphan_segments: 保留兼容格式的對話歷史 ID（不嘗試解析）: {vec_id}")
                                is_orphan = False
                        elif vec_id.startswith('legacy_'):
                            # 一律視為合法舊版格式，不做刪除（避免誤刪）
                            is_orphan = False

                    if is_orphan:
                        orphan_ids.append(vec_id)

                if orphan_ids:
                    self.logger.info(f"cleanup_orphan_segments: 頻道 {channel_id} 初步計算出 {len(orphan_ids)} 個待刪除孤兒 ID，示例: {orphan_ids[:10]}")
                    candidate_deletions[channel_id] = orphan_ids

            # 安全護欄：全域批次門檻
            total_to_delete = sum(len(v) for v in candidate_deletions.values())
            if total_to_delete > 0:
                self.logger.info(f"cleanup_orphan_segments: 計畫刪除總計 {total_to_delete} 個孤兒向量，涉及 {len(candidate_deletions)} 個頻道。")
            if total_to_delete > 1000:
                self.logger.critical(f"cleanup_orphan_segments: 偵測到異常大量刪除（{total_to_delete} > 1000），為避免災難性資料遺失，本次清理將被跳過。")
            else:
                # 執行每頻道一次的批次刪除；同時加入每頻道的安全門檻
                for channel_id, ids_to_remove in candidate_deletions.items():
                    if len(ids_to_remove) > 1000:
                        self.logger.critical(f"cleanup_orphan_segments: 頻道 {channel_id} 的刪除數量過大（{len(ids_to_remove)} > 1000），已跳過此頻道的刪除。")
                        continue
                    try:
                        removed_count = self.vector_manager.remove_vectors(channel_id, ids_to_remove)
                        self.logger.info(f"cleanup_orphan_segments: 頻道 {channel_id} 已批次移除 {removed_count} 個向量。")
                        if removed_count > 0:
                            removed_stats[channel_id] = removed_stats.get(channel_id, 0) + removed_count
                    except Exception as e:
                        await func.func.report_error(e, f"Batch removal of orphan vectors from channel {channel_id}")

            total_removed = sum(removed_stats.values())
            if total_removed > 0:
                self.logger.info(f"孤兒向量清理完成，共移除了 {total_removed} 個向量。")
            else:
                self.logger.info("未找到需要清理的孤兒向量。")

            return removed_stats

        except Exception as e:
            await func.func.report_error(e, "Orphan segment cleanup")
            return removed_stats

    async def initialize(self) -> bool:
        """初始化記憶系統

        Returns:
            bool: 是否成功初始化
        """
        if self._initialized:
            self.logger.info("記憶系統已經初始化，跳過重複初始化")
            return True

        try:
            # 初始化啟動日誌管理器
            startup_logger = StartupLoggerManager.get_instance(self.logger)
            if startup_logger:
                startup_logger.start_startup_phase()

            self.logger.info("開始初始化記憶系統...")
            self.logger.info("檢查初始化狀態: _initialized=%s, _enabled=%s", self._initialized, self._enabled)
            
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
            self.logger.info("開始初始化向量組件...")
            try:
                await self._initialize_vector_components()
                self.logger.info("向量組件初始化成功")
            except AttributeError as e:
                self.logger.error(f"向量組件初始化失敗: 方法 '_initialize_vector_components' 不存在 - {e}")
                self.logger.error("這表示記憶系統程式碼不完整，缺少關鍵的初始化方法")
                # 繼續執行，不拋出異常以允許系統在降級模式下運行
            except Exception as e:
                self.logger.error(f"向量組件初始化時發生其他錯誤: {e}")
                raise
            
            # 初始化分割服務
            await self._initialize_segmentation_service()
            
            self._initialized = True
            
            # 結束啟動階段並輸出摘要
            if startup_logger:
                startup_logger.end_startup_phase()
            
            self.logger.info(f"記憶系統初始化完成 (配置檔案: {self.current_profile.name})")

            # 啟動完成後：進行向量索引健康檢查與快速修復（不中斷啟動）
            try:
                if self.vector_manager and self.current_profile and self.current_profile.vector_enabled:
                    self.logger.info("vector_index_health_check_start")
                    results = await asyncio.get_event_loop().run_in_executor(
                        None, self.vector_manager.check_and_repair_all_indices
                    )
                    self.logger.info("vector_index_health_check_finish | summary=%s", results.get('summary', {}))
                    # 若仍有高風險索引，提出警告但不中斷
                    problematic = [
                        (cid, r) for cid, r in results.items()
                        if isinstance(r, dict) and r.get('has_issues', False) and not r.get('repair_successful', False)
                    ]
                    if problematic:
                        self.logger.warning(
                            "vector_index_health_check_finish | residual_risk=%d 建議執行離線重建以獲得最佳完整性",
                            len(problematic)
                        )
                else:
                    self.logger.info("vector_index_health_check_skip | vector_disabled_or_manager_missing")
            except Exception as ve:
                self.logger.warning("vector_index_health_check_error | reason=%s", str(ve))

            return True
            
        except Exception as e:
            # 確保啟動階段結束
            startup_logger = get_startup_logger()
            if startup_logger:
                startup_logger.log_error(f"記憶系統初始化失敗: {e}")
                startup_logger.end_startup_phase()
            
            await func.func.report_error(e, "Memory system initialization")
            raise MemorySystemError(f"記憶系統初始化失敗: {e}")
    
    async def _load_configuration(self) -> None:
        """載入配置"""
        try:
            # 在非同步環境中執行配置載入
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.config.load_config)
            
        except Exception as e:
            await func.func.report_error(e, "Configuration loading")
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
                db_path,
                self.bot
            )
            
        except Exception as e:
            await func.func.report_error(e, "Database initialization")
            raise DatabaseError(f"初始化資料庫失敗: {e}")
    
    
    
    
    async def _load_existing_indices(self) -> None:
        """掃描現有的索引檔案並記錄其狀態，但不立即載入。"""
        try:
            if not self.vector_manager or not self.current_profile.vector_enabled or self.current_profile.disable_vector_database:
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
            await func.func.report_error(e, "Scanning existing indices")
    
    async def _ensure_index_loaded(self, channel_id: str) -> None:
        """確保指定頻道的索引已載入記憶體，並管理 LRU 快取。"""
        if not self.vector_manager or not self.current_profile.vector_enabled or self.current_profile.disable_vector_database:
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
                    await func.func.report_error(e, f"Index loading for channel {channel_id}")
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
            await func.func.report_error(e, "Text segmentation service initialization")
            # 不拋出例外，允許系統在無分割功能的情況下運行
            if self.segmentation_config:
                self.segmentation_config.enabled = False

    async def _initialize_vector_components(self) -> None:
        """初始化向量相關組件"""
        try:
            self.logger.info("開始初始化向量組件...")

            # 檢查是否啟用向量功能
            if not self.current_profile or not self.current_profile.vector_enabled:
                self.logger.info("向量功能已停用，跳過向量組件初始化")
                return

            # 檢查向量資料庫是否被禁用
            if self.current_profile.disable_vector_database:
                self.logger.info("向量資料庫已被禁用，使用備用記憶體管理器")
                await self._initialize_fallback_memory_manager()
                return

            # 初始化嵌入服務
            self.logger.info("初始化嵌入服務...")
            try:
                from .embedding_service import embedding_service_manager
                self.embedding_service = embedding_service_manager.get_service(self.current_profile)
                self.logger.info(f"嵌入服務初始化成功 (模型: {self.current_profile.embedding_model})")
            except Exception as e:
                self.logger.error(f"嵌入服務初始化失敗: {e}")
                # 降級到備用記憶體管理器
                await self._initialize_fallback_memory_manager()
                return

            # 初始化重新排序服務
            self.logger.info("初始化重新排序服務...")
            try:
                self.reranker_service = RerankerService(self.current_profile)
                self.logger.info("重新排序服務初始化成功")
            except Exception as e:
                self.logger.warning(f"重新排序服務初始化失敗: {e}")
                # 這不是致命錯誤，可以繼續

            # 初始化向量管理器
            self.logger.info("初始化向量管理器...")
            try:
                self.vector_manager = get_vector_manager(
                    profile=self.current_profile,
                    storage_path=Path("data/memory/vectors")
                )
                self.logger.info("向量管理器初始化成功")
            except Exception as e:
                self.logger.error(f"向量管理器初始化失敗: {e}")
                # 降級到備用記憶體管理器
                await self._initialize_fallback_memory_manager()
                return

            # 初始化搜尋引擎
            self.logger.info("初始化搜尋引擎...")
            try:
                self.search_engine = SearchEngine(
                    profile=self.current_profile,
                    embedding_service=self.embedding_service,
                    vector_manager=self.vector_manager,
                    database_manager=self.db_manager,
                    bot=self.bot
                )
                self.logger.info("搜尋引擎初始化成功")
            except Exception as e:
                self.logger.error(f"搜尋引擎初始化失敗: {e}")
                # 這不是致命錯誤，可以繼續

            self.logger.info("向量組件初始化完成")

        except Exception as e:
            await func.func.report_error(e, "Vector components initialization")
            # 嘗試降級到備用記憶體管理器
            try:
                await self._initialize_fallback_memory_manager()
            except Exception as fallback_error:
                await func.func.report_error(fallback_error, "Fallback memory manager initialization")
                raise MemorySystemError(f"無法初始化任何記憶體系統: {e}")

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
            await func.func.report_error(e, "Memory stats retrieval")
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
            asyncio.create_task(func.func.report_error(e, "Storage size calculation"))
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
            await func.func.report_error(e, "Message storage")
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

    def _parse_timestamp_to_utc(self, ts) -> datetime:
        """將輸入的字串或 datetime 轉為有時區的 UTC datetime。"""
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                # 後備解析：處理末尾帶 'Z' 的 ISO 字串
                if ts.endswith('Z'):
                    dt = datetime.fromisoformat(ts[:-1])
                else:
                    raise
        elif isinstance(ts, datetime):
            dt = ts
        else:
            raise TypeError(f"不支援的 timestamp 類型: {type(ts)}")

        if dt.tzinfo is None:
            # 無時區 -> 視為 UTC
            return dt.replace(tzinfo=timezone.utc)
        # 有時區 -> 轉為 UTC
        return dt.astimezone(timezone.utc)

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
            asyncio.create_task(func.func.report_error(e, "Sync message storage"))
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
            # 為 message_id 加上 "msg_" 前綴，以區分 segment ID
            success = self.vector_manager.add_vectors(
                channel_id=channel_id,
                vectors=np.array([embedding]),
                ids=[f"msg_{message_id}"]
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
            await func.func.report_error(e, "Message vector storage")
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
            await func.func.report_error(e, "Message segmentation processing")
    
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
            messages.sort(key=lambda m: self._parse_timestamp_to_utc(m['timestamp']))
            
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
                        timestamp=self._parse_timestamp_to_utc(message_data['timestamp']),
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
            await func.func.report_error(e, f"Async segmentation processing for channel {channel_id}")
    
    async def _post_process_completed_segment(self, segment) -> None:
        """後處理已完成的片段

        Args:
            segment: 已完成的片段物件
        """
        try:
            if self.current_profile.vector_enabled:
                await self._add_segment_to_vector_index(segment)
        except Exception as e:
            await func.func.report_error(e, f"Post-processing of segment {segment.id}")
    
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
            await func.func.report_error(e, "Adding segment to vector index")
    
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
            asyncio.create_task(func.func.report_error(e, "Storing embedding to database"))
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
            await func.func.report_error(e, "Ensuring indices directory")
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
            await func.func.report_error(e, "Diagnosing index storage issue")
    
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
            await func.func.report_error(e, "Memory search")
            raise SearchError(f"記憶搜尋失敗: {e}")
    
    def _cleanup_sync(self) -> None:
        """同步清理所有阻塞型資源，集中於單一背景執行緒中執行。
        
        注意：
        - 僅執行同步/阻塞操作（磁碟 I/O、GPU 釋放、gc.collect、關閉資料庫連線等）
        - 非同步清理（協程）請於 async cleanup()/shutdown() 先行 await
        """
        try:
            # 1) 向量管理器：儲存所有索引、釋放 GPU/快取、最佳化記憶體（完全同步）
            if self.vector_manager and hasattr(self.vector_manager, "_cleanup_sync"):
                try:
                    # 若 VectorManager 已關閉則跳過重複清理
                    if not getattr(self.vector_manager, "_shutdown", False):
                        self.vector_manager._cleanup_sync()
                except Exception as e:
                    self.logger.error(f"VectorManager 同步清理失敗: {e}")
                    asyncio.create_task(func.func.report_error(e, "VectorManager sync cleanup"))
            
            # 2) 搜尋引擎：若有同步 cleanup，則在此執行
            try:
                if self.search_engine and hasattr(self.search_engine, "cleanup"):
                    cleanup_func = getattr(self.search_engine, "cleanup")
                    if cleanup_func and not asyncio.iscoroutinefunction(cleanup_func):
                        cleanup_func()
            except Exception as e:
                self.logger.error(f"SearchEngine 同步清理失敗: {e}")
                asyncio.create_task(func.func.report_error(e, "SearchEngine sync cleanup"))
            
            # 3) Reranker 服務：同步清理（或退回 clear_cache）
            try:
                if self.reranker_service:
                    cleanup_func = getattr(self.reranker_service, "cleanup", None)
                    if cleanup_func and not asyncio.iscoroutinefunction(cleanup_func):
                        cleanup_func()
                    elif hasattr(self.reranker_service, "clear_cache"):
                        self.reranker_service.clear_cache()
            except Exception as e:
                self.logger.error(f"RerankerService 同步清理失敗: {e}")
                asyncio.create_task(func.func.report_error(e, "RerankerService sync cleanup"))
            
            # 4) Embedding 服務：同步清理（若提供）
            try:
                if self.embedding_service:
                    cleanup_func = getattr(self.embedding_service, "cleanup", None)
                    if cleanup_func and not asyncio.iscoroutinefunction(cleanup_func):
                        cleanup_func()
            except Exception as e:
                self.logger.error(f"EmbeddingService 同步清理失敗: {e}")
                asyncio.create_task(func.func.report_error(e, "EmbeddingService sync cleanup"))
            
            # 5) 資料庫連線：同步關閉
            try:
                if self.db_manager:
                    self.db_manager.close_connections()
            except Exception as e:
                self.logger.error(f"DatabaseManager 關閉連線失敗: {e}")
                asyncio.create_task(func.func.report_error(e, "DatabaseManager connection closing"))
            
            # 6) 最後執行一次垃圾回收與 GPU 快取清除（若 VectorManager 未處理）
            try:
                gc.collect()
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"_cleanup_sync 執行失敗: {e}")
            asyncio.create_task(func.func.report_error(e, "Sync cleanup"))
    
    async def cleanup(self) -> None:
        """清理記憶體資源與快取：非同步協程僅保留一次 to_thread 呼叫。"""
        try:
            self.logger.info("開始記憶體系統清理...")
            
            # 先處理協程型清理（不會造成執行緒風暴）
            try:
                if self.search_engine and hasattr(self.search_engine, "cleanup") and asyncio.iscoroutinefunction(self.search_engine.cleanup):
                    await self.search_engine.cleanup()
            except Exception as e:
                self.logger.error(f"SearchEngine 清理失敗: {e}")
                await func.func.report_error(e, "SearchEngine cleanup")
            
            try:
                if self.reranker_service and hasattr(self.reranker_service, "cleanup") and asyncio.iscoroutinefunction(self.reranker_service.cleanup):
                    await self.reranker_service.cleanup()
            except Exception as e:
                self.logger.error(f"RerankerService 清理失敗: {e}")
                await func.func.report_error(e, "RerankerService cleanup")
            
            try:
                if self.embedding_service and hasattr(self.embedding_service, "cleanup") and asyncio.iscoroutinefunction(self.embedding_service.cleanup):
                    await self.embedding_service.cleanup()
            except Exception as e:
                self.logger.error(f"EmbeddingService 清理失敗: {e}")
                await func.func.report_error(e, "EmbeddingService cleanup")
            
            # 將所有阻塞的同步清理整合成單一背景任務
            await asyncio.to_thread(self._cleanup_sync)
            
            self._initialized = False
            self.logger.info("記憶體系統清理完成")
        except Exception as e:
            self.logger.error(f"記憶體清理時發生嚴重錯誤: {e}")
            await func.func.report_error(e, "Memory system cleanup")
    
    async def shutdown(self) -> None:
        """優雅關閉 MemoryManager，集中釋放所有下游資源。"""
        try:
            # 先取消並等待所有背景任務，避免 CancelledError 外漏
            try:
                bg_tasks = [t for t in getattr(self, "_bg_tasks", set()) if not t.done()]
                for t in bg_tasks:
                    t.cancel()
                if bg_tasks:
                    await asyncio.gather(*bg_tasks, return_exceptions=True)
            except Exception as e:
                self.logger.warning(f"取消背景任務時發生錯誤: {e}")
                await func.func.report_error(e, "Background task cancellation during shutdown")
            
            # 統一走 cleanup，內部只會進行一次 to_thread 同步清理
            await self.cleanup()
        except Exception as e:
            self.logger.error(f"關閉 MemoryManager發生嚴重錯誤: {e}")
            await func.func.report_error(e, "MemoryManager shutdown")
            
    async def _initialize_fallback_memory_manager(self) -> None:
        """初始化備用記憶體管理器"""
        try:
            if not self.db_manager:
                self.logger.warning("資料庫管理器未初始化，無法初始化備用記憶體管理器")
                return

            # 從配置中取得快取設定
            memory_config = self.config.get_memory_config()
            cache_config = memory_config.get("cache", {})
            cache_size = cache_config.get("max_size_mb", 512)
            cache_ttl = cache_config.get("ttl_seconds", 3600)

            # 初始化備用記憶體管理器
            self.fallback_memory_manager = FallbackMemoryManager(
                db_manager=self.db_manager,
                cache_size=cache_size,
                cache_ttl=cache_ttl
            )

            self.logger.info("備用記憶體管理器初始化完成")

        except Exception as e:
            await func.func.report_error(e, "Fallback memory manager initialization")
            self.fallback_memory_manager = None