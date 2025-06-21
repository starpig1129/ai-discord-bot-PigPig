"""啟動日誌優化管理器

提供記憶系統啟動時的日誌聚合和簡化功能，
減少冗餘的 INFO 級別日誌輸出，同時保持除錯資訊的完整性。
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from pathlib import Path


@dataclass
class StartupMetrics:
    """啟動指標資料類別"""
    total_indices: int = 0
    loaded_indices: int = 0
    failed_indices: int = 0
    gpu_memory_checks: int = 0
    gpu_memory_warnings: int = 0
    startup_time: float = 0.0
    batch_count: int = 0
    errors: List[str] = field(default_factory=list)


class StartupLogger:
    """啟動日誌管理器
    
    負責在機器人啟動期間聚合和簡化日誌輸出，
    避免產生過多的 INFO 級別訊息。
    """
    
    def __init__(self, logger: logging.Logger):
        """初始化啟動日誌管理器
        
        Args:
            logger: 原始 logger 實例
        """
        self.logger = logger
        self.metrics = StartupMetrics()
        self.start_time = time.time()
        self.is_startup_mode = True
        self.last_gpu_memory_log = 0.0
        self.gpu_memory_log_interval = 30.0  # 30秒間隔
        
        # 追蹤已處理的項目，避免重複日誌
        self.processed_channels: Set[str] = set()
        self.gpu_warnings_shown: Set[str] = set()
        
    def start_startup_phase(self) -> None:
        """開始啟動階段"""
        self.is_startup_mode = True
        self.start_time = time.time()
        self.logger.info("🚀 記憶系統啟動中...")
        
    def end_startup_phase(self) -> None:
        """結束啟動階段並輸出摘要"""
        self.is_startup_mode = False
        self.metrics.startup_time = time.time() - self.start_time
        self._log_startup_summary()
        
    def log_gpu_memory_check(
        self, 
        total_mb: int, 
        free_mb: int, 
        used_percent: float,
        force_log: bool = False
    ) -> None:
        """記錄 GPU 記憶體檢查（節流處理）
        
        Args:
            total_mb: 總記憶體（MB）
            free_mb: 可用記憶體（MB）
            used_percent: 使用率百分比
            force_log: 是否強制記錄日誌
        """
        self.metrics.gpu_memory_checks += 1
        current_time = time.time()
        
        # 節流：只在間隔時間後或強制記錄時輸出
        if (force_log or 
            current_time - self.last_gpu_memory_log > self.gpu_memory_log_interval):
            
            if self.is_startup_mode:
                # 啟動模式：簡化日誌
                self.logger.debug(
                    f"GPU 記憶體: {free_mb}MB 可用 / {total_mb}MB 總計 "
                    f"(使用率: {used_percent:.1f}%)"
                )
            else:
                # 正常模式：詳細日誌
                self.logger.info(
                    f"GPU 記憶體狀態: 總計 {total_mb}MB, "
                    f"可用 {free_mb}MB, 使用率 {used_percent:.1f}%"
                )
            
            self.last_gpu_memory_log = current_time
            
        # 記錄警告（如果需要）
        if used_percent > 85.0:
            warning_key = f"high_usage_{used_percent:.0f}"
            if warning_key not in self.gpu_warnings_shown:
                self.logger.warning(f"GPU 記憶體使用率過高: {used_percent:.1f}%")
                self.gpu_warnings_shown.add(warning_key)
                self.metrics.gpu_memory_warnings += 1
                
    def log_index_loading_start(self, total_count: int) -> None:
        """記錄索引載入開始
        
        Args:
            total_count: 總索引數量
        """
        self.metrics.total_indices = total_count
        if total_count == 0:
            self.logger.info("📂 沒有找到現有的索引檔案")
        else:
            self.logger.info(f"📂 找到 {total_count} 個現有索引，開始載入...")
            
    def log_batch_progress(
        self, 
        batch_num: int, 
        total_batches: int, 
        batch_loaded: int,
        batch_failed: int
    ) -> None:
        """記錄批次進度（簡化版）
        
        Args:
            batch_num: 當前批次編號
            total_batches: 總批次數
            batch_loaded: 本批次載入成功數
            batch_failed: 本批次載入失敗數
        """
        self.metrics.loaded_indices += batch_loaded
        self.metrics.failed_indices += batch_failed
        self.metrics.batch_count = batch_num
        
        # 只在關鍵節點記錄進度（避免過多日誌）
        if batch_num == 1 or batch_num == total_batches or batch_num % 5 == 0:
            progress_percent = (batch_num / total_batches) * 100
            self.logger.debug(
                f"📊 載入進度: {batch_num}/{total_batches} 批次 "
                f"({progress_percent:.0f}%) - "
                f"成功 {self.metrics.loaded_indices}，"
                f"失敗 {self.metrics.failed_indices}"
            )
            
    def log_channel_index_ready(self, channel_id: str, is_new: bool = False) -> None:
        """記錄頻道索引準備就緒（去重處理）
        
        Args:
            channel_id: 頻道 ID
            is_new: 是否為新建索引
        """
        if channel_id in self.processed_channels:
            return
            
        self.processed_channels.add(channel_id)
        
        if self.is_startup_mode:
            # 啟動模式：僅 debug 級別
            status = "新建" if is_new else "載入"
            self.logger.debug(f"頻道 {channel_id} 索引已{status}")
        else:
            # 正常模式：info 級別
            status = "新建" if is_new else "載入"
            self.logger.info(f"頻道 {channel_id} 的向量索引已準備就緒（{status}）")
            
    def log_gpu_index_migration(self, channel_id: str, estimated_mb: int) -> None:
        """記錄 GPU 索引遷移（簡化）
        
        Args:
            channel_id: 頻道 ID
            estimated_mb: 預估記憶體使用量
        """
        if self.is_startup_mode:
            # 啟動模式：簡化日誌
            self.logger.debug(f"索引 {channel_id} 已移至 GPU ({estimated_mb}MB)")
        else:
            # 正常模式：詳細日誌
            self.logger.info(f"索引已移至 GPU（預估記憶體: {estimated_mb}MB）")
            
    def log_error(self, error_msg: str) -> None:
        """記錄錯誤訊息
        
        Args:
            error_msg: 錯誤訊息
        """
        self.metrics.errors.append(error_msg)
        self.logger.error(error_msg)
        
    def log_warning(self, warning_msg: str, deduplicate: bool = True) -> None:
        """記錄警告訊息
        
        Args:
            warning_msg: 警告訊息
            deduplicate: 是否去重
        """
        if deduplicate and warning_msg in self.gpu_warnings_shown:
            return
            
        if deduplicate:
            self.gpu_warnings_shown.add(warning_msg)
            
        self.logger.warning(warning_msg)
        
    def _log_startup_summary(self) -> None:
        """記錄啟動摘要"""
        success_rate = 0.0
        if self.metrics.total_indices > 0:
            success_rate = (self.metrics.loaded_indices / self.metrics.total_indices) * 100
            
        # 主要摘要
        self.logger.info(
            f"✅ 記憶系統啟動完成 "
            f"(耗時: {self.metrics.startup_time:.1f}秒)"
        )
        
        # 索引載入摘要
        if self.metrics.total_indices > 0:
            self.logger.debug(
                f"📋 索引載入摘要: "
                f"{self.metrics.loaded_indices}/{self.metrics.total_indices} 成功 "
                f"({success_rate:.1f}%)，"
                f"共處理 {self.metrics.batch_count} 個批次"
            )
        else:
            self.logger.info("📋 無現有索引需要載入")
            
        # GPU 記憶體摘要
        if self.metrics.gpu_memory_checks > 0:
            self.logger.debug(
                f"🔧 GPU 記憶體檢查: {self.metrics.gpu_memory_checks} 次，"
                f"警告: {self.metrics.gpu_memory_warnings} 次"
            )
            
        # 錯誤摘要
        if self.metrics.errors:
            self.logger.warning(f"⚠️  啟動期間發生 {len(self.metrics.errors)} 個錯誤")
            for i, error in enumerate(self.metrics.errors[:3], 1):  # 最多顯示3個錯誤
                self.logger.warning(f"   {i}. {error}")
            if len(self.metrics.errors) > 3:
                self.logger.warning(f"   ... 還有 {len(self.metrics.errors) - 3} 個錯誤")


class StartupLoggerManager:
    """啟動日誌管理器單例"""
    
    _instance: Optional[StartupLogger] = None
    
    @classmethod
    def get_instance(cls, logger: Optional[logging.Logger] = None) -> Optional[StartupLogger]:
        """取得啟動日誌管理器實例
        
        Args:
            logger: logger 實例（首次呼叫時需要）
            
        Returns:
            StartupLogger 實例或 None
        """
        if cls._instance is None and logger is not None:
            cls._instance = StartupLogger(logger)
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """重置實例（用於測試）"""
        cls._instance = None


def get_startup_logger(logger: Optional[logging.Logger] = None) -> Optional[StartupLogger]:
    """取得啟動日誌管理器的便利函數
    
    Args:
        logger: logger 實例
        
    Returns:
        StartupLogger 實例或 None
    """
    return StartupLoggerManager.get_instance(logger)