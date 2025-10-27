import asyncio
"""向量管理模組

提供 FAISS 向量索引的建立、管理和搜尋功能。
支援 GPU/CPU 自動切換、批次操作和索引優化。
"""

import gc
import logging
import os
import pickle
import threading
import time
import tempfile
import shutil
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Set

import faiss
import numpy as np
from function import func
import asyncio

from .config import MemoryProfile
from .exceptions import VectorOperationError, IndexIntegrityError
from .startup_logger import get_startup_logger

# 嘗試導入 GPU 記憶體監控模組
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False
    pynvml = None

# GPU 狀態管理
class GPUManager:
    """GPU 狀態管理器，提供延遲初始化和自動恢復機制"""

    _instance = None
    _initialized = False
    _nvml_initialized = False
    _gpu_available = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.logger = logging.getLogger(__name__)
            self._initialized = True
            self._init_gpu_status()

    def _init_gpu_status(self):
        """初始化 GPU 狀態，延遲且安全的初始化"""
        try:
            # 檢查 PyTorch CUDA 可用性
            if TORCH_AVAILABLE and torch.cuda.is_available():
                self._gpu_available = True
                self.logger.info(f"偵測到 PyTorch CUDA 可用: {torch.cuda.get_device_name(0)}")
            else:
                self.logger.info("PyTorch CUDA 不可用")

            # 檢查 NVML 可用性（延遲初始化）
            if PYNVML_AVAILABLE and pynvml is not None:
                try:
                    pynvml.nvmlInit()
                    self._nvml_initialized = True
                    self._gpu_available = True
                    device_count = pynvml.nvmlDeviceGetCount()
                    self.logger.info(f"NVML 初始化成功，偵測到 {device_count} 個 GPU 設備")
                except Exception as e:
                    self.logger.warning(f"NVML 初始化失敗: {e}")
                    self._nvml_initialized = False
                    self._gpu_available = False
            else:
                self.logger.debug("NVML 模組不可用")

        except Exception as e:
            asyncio.create_task(func.report_error(e, "GPU status initialization"))
            self.logger.error(f"GPU 狀態初始化失敗: {e}", exc_info=True)
            self._gpu_available = False

    def is_gpu_available(self) -> bool:
        """檢查 GPU 是否可用"""
        return self._gpu_available

    def ensure_nvml_initialized(self) -> bool:
        """確保 NVML 已初始化，如果失敗則嘗試恢復"""
        if not PYNVML_AVAILABLE or pynvml is None:
            return False

        if not self._nvml_initialized:
            try:
                pynvml.nvmlInit()
                self._nvml_initialized = True
                self.logger.info("NVML 恢復初始化成功")
                return True
            except Exception as e:
                asyncio.create_task(func.report_error(e, "NVML re-initialization"))
                self.logger.error(f"NVML 重新初始化失敗: {e}", exc_info=True)
                return False

        return True

    def shutdown(self):
        """關閉 GPU 管理器"""
        if self._nvml_initialized and PYNVML_AVAILABLE and pynvml is not None:
            try:
                pynvml.nvmlShutdown()
                self._nvml_initialized = False
                self.logger.debug("NVML 已關閉")
            except Exception as e:
                asyncio.create_task(func.report_error(e, "NVML shutdown"))
                self.logger.error(f"NVML 關閉失敗: {e}", exc_info=True)

# 全域 GPU 管理器實例
gpu_manager = GPUManager()


class GPUMemoryManager:
    """GPU 記憶體管理器

    負責監控和管理 GPU 記憶體使用，提供優雅降級機制。
    """

    def __init__(self, max_memory_mb: int = 1024):
        """初始化 GPU 記憶體管理器

        Args:
            max_memory_mb: FAISS GPU 最大記憶體使用量（MB）
        """
        self.logger = logging.getLogger(__name__)
        self.max_memory_mb = max_memory_mb
        self._gpu_resource: Optional[faiss.StandardGpuResources] = None
        self._memory_lock = threading.Lock()
        self._last_memory_check = 0
        self._memory_cache_timeout = 1.0  # 快取記憶體資訊1秒
        self._cached_memory_info = (0, 0, 0.0)
        self._fallback_mode = False  # 降級模式標記
        self._recovery_attempts = 0   # 恢復嘗試次數
        self._max_recovery_attempts = 3

    def get_gpu_memory_info(self) -> Tuple[int, int, float]:
        """取得 GPU 記憶體資訊（支援快取和多種後備方案）

        Returns:
            Tuple[int, int, float]: (總記憶體MB, 可用記憶體MB, 使用率%)
        """
        # 檢查快取是否過期
        current_time = time.time()
        if current_time - self._last_memory_check < self._memory_cache_timeout:
            return self._cached_memory_info

        try:
            # 嘗試使用 NVML
            if gpu_manager.ensure_nvml_initialized():
                try:
                    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    total_mb = memory_info.total // (1024 * 1024)
                    free_mb = memory_info.free // (1024 * 1024)
                    used_percent = ((memory_info.total - memory_info.free) / memory_info.total) * 100

                    # 更新快取
                    self._cached_memory_info = (total_mb, free_mb, used_percent)
                    self._last_memory_check = current_time
                    return self._cached_memory_info
                except Exception as e:
                    asyncio.create_task(func.report_error(e, "NVML memory check"))
                    self.logger.debug(f"NVML 記憶體檢查失敗: {e}")

            # 嘗試使用 PyTorch CUDA
            if TORCH_AVAILABLE and torch.cuda.is_available():
                try:
                    total_mb = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
                    allocated_mb = torch.cuda.memory_allocated(0) // (1024 * 1024)
                    reserved_mb = torch.cuda.memory_reserved(0) // (1024 * 1024)
                    free_mb = total_mb - reserved_mb
                    used_percent = (reserved_mb / total_mb) * 100

                    # 更新快取
                    self._cached_memory_info = (total_mb, free_mb, used_percent)
                    self._last_memory_check = current_time
                    return self._cached_memory_info
                except Exception as e:
                    asyncio.create_task(func.report_error(e, "PyTorch CUDA memory check"))
                    self.logger.debug(f"PyTorch CUDA 記憶體檢查失敗: {e}")

            # CPU 模式備份方案
            self.logger.debug("無法取得 GPU 記憶體資訊，使用 CPU 模式")
            self._cached_memory_info = (0, 0, 0.0)
            self._last_memory_check = current_time
            return self._cached_memory_info

        except Exception as e:
            asyncio.create_task(func.report_error(e, "GPU memory info retrieval"))
            self.logger.error(f"獲取 GPU 記憶體資訊時發生錯誤: {e}", exc_info=True)
            self._cached_memory_info = (0, 0, 0.0)
            self._last_memory_check = current_time
            return self._cached_memory_info
    
    def is_memory_available(self, required_mb: int = 512) -> bool:
        """檢查是否有足夠的 GPU 記憶體（支援自動恢復）

        Args:
            required_mb: 需要的記憶體量（MB）

        Returns:
            bool: 是否有足夠記憶體
        """
        try:
            total_mb, free_mb, used_percent = self.get_gpu_memory_info()

            # 如果 GPU 完全不可用，嘗試自動恢復
            if total_mb == 0 and not self._fallback_mode:
                self.logger.info("GPU 記憶體資訊不可用，嘗試自動恢復")
                if self._attempt_gpu_recovery():
                    # 重新檢查記憶體
                    total_mb, free_mb, used_percent = self.get_gpu_memory_info()

            # 如果仍然無法取得 GPU 資訊，使用 CPU 模式
            if total_mb == 0:
                self.logger.debug("使用 CPU 模式，記憶體檢查通過")
                return True

            # 檢查可用記憶體
            if free_mb < required_mb:
                self.logger.warning(f"GPU 記憶體不足: 需要 {required_mb}MB，可用 {free_mb}MB")
                # 嘗試清理後重試
                if self._attempt_memory_recovery(required_mb):
                    _, free_mb_after, _ = self.get_gpu_memory_info()
                    if free_mb_after >= required_mb:
                        return True
                return False

            # 檢查使用率
            if used_percent > 75.0:
                self.logger.warning(f"GPU 記憶體使用率過高: {used_percent:.1f}%")
                # 主動觸發記憶體清理
                if self._trigger_memory_cleanup():
                    # 再次檢查記憶體狀態
                    _, free_mb_after, used_percent_after = self.get_gpu_memory_info()
                    if used_percent_after > 75.0:
                        return False

            return True

        except Exception as e:
            asyncio.create_task(func.report_error(e, "GPU memory availability check"))
            # 發生錯誤時嘗試恢復
            if self._attempt_gpu_recovery():
                return self.is_memory_available(required_mb)
            return False

    def _attempt_gpu_recovery(self) -> bool:
        """嘗試 GPU 恢復機制

        Returns:
            bool: 是否恢復成功
        """
        try:
            self.logger.info("開始 GPU 恢復程序")

            # 清理 GPU 記憶體
            self.clear_gpu_memory()

            # 確保 NVML 初始化
            if gpu_manager.ensure_nvml_initialized():
                self.logger.info("GPU 恢復成功")
                return True

            return False

        except Exception as e:
            asyncio.create_task(func.report_error(e, "GPU recovery attempt"))
            return False

    def _attempt_memory_recovery(self, required_mb: int) -> bool:
        """嘗試記憶體恢復機制

        Args:
            required_mb: 需要的記憶體量

        Returns:
            bool: 是否恢復成功
        """
        try:
            self.logger.info(f"嘗試記憶體恢復，需要 {required_mb}MB")

            # 多次清理嘗試
            for attempt in range(3):
                self._trigger_memory_cleanup()

                _, free_mb, used_percent = self.get_gpu_memory_info()

                if free_mb >= required_mb:
                    self.logger.info(f"記憶體恢復成功 (嘗試 {attempt + 1}/3): 可用 {free_mb}MB")
                    return True

                if attempt < 2:  # 最後一次嘗試前等待
                    time.sleep(0.5 * (attempt + 1))

            self.logger.warning("記憶體恢復嘗試失敗")
            return False

        except Exception as e:
            asyncio.create_task(func.report_error(e, "GPU memory recovery attempt"))
            return False
    
    def get_gpu_resource(self) -> 'Optional[faiss.StandardGpuResources]':
        """取得 GPU 資源實例（單例模式，支援自動恢復）

        Returns:
            Optional[faiss.StandardGpuResources]: GPU 資源實例
        """
        with self._memory_lock:
            # 如果已經處於降級模式且恢復嘗試次數過多，直接返回 None
            if (self._fallback_mode and
                self._recovery_attempts >= self._max_recovery_attempts):
                return None

            # 如果資源已存在且正常，直接返回
            if self._gpu_resource is not None:
                try:
                    # 簡單測試資源是否仍然有效
                    temp_memory_mb = min(self.max_memory_mb // 4, 512)
                    self._gpu_resource.setTempMemory(temp_memory_mb * 1024 * 1024)
                    return self._gpu_resource
                except Exception as e:
                    self.logger.warning(f"現有 GPU 資源失效: {e}")
                    self._gpu_resource = None

            # 檢查基本條件
            if not hasattr(faiss, 'StandardGpuResources'):
                if not self._fallback_mode:
                    self.logger.info("未偵測到 faiss-gpu，將使用 CPU 模式")
                    self._fallback_mode = True
                return None

            # 檢查 GPU 可用性
            if not gpu_manager.is_gpu_available():
                if not self._fallback_mode:
                    self.logger.info("GPU 不可用，自動降級到 CPU 模式")
                    self._fallback_mode = True
                return None

            try:
                # 檢查記憶體是否可用
                if not self.is_memory_available(self.max_memory_mb):
                    self.logger.warning("GPU 記憶體不足，無法建立 GPU 資源")
                    self._fallback_mode = True
                    self._recovery_attempts += 1
                    return None

                self.logger.debug(f"開始建立 GPU 資源，記憶體限制: {self.max_memory_mb}MB")

                # 簡化的 GPU 資源建立
                gpu_resource = faiss.StandardGpuResources()

                # 設定記憶體限制
                temp_memory_mb = min(self.max_memory_mb // 4, 512)
                gpu_resource.setTempMemory(temp_memory_mb * 1024 * 1024)

                # 診斷日誌：記錄方法調用前的狀態
                self.logger.info(f"GPU 資源類型: {type(gpu_resource)}")
                self.logger.info(f"GPU 資源方法清單: {[method for method in dir(gpu_resource) if 'Stream' in method or 'Null' in method]}")

                # 設定定時記憶體清理
                self.logger.info("嘗試調用 setDefaultNullStreamAllDevices()")
                try:
                    # 檢查方法簽名
                    import inspect
                    method_signature = inspect.signature(gpu_resource.setDefaultNullStreamAllDevices)
                    self.logger.info(f"setDefaultNullStreamAllDevices 簽名: {method_signature}")

                    # 嘗試不傳參數調用
                    gpu_resource.setDefaultNullStreamAllDevices()
                    self.logger.info("setDefaultNullStreamAllDevices() 調用成功（無參數）")
                except TypeError as e:
                    self.logger.error(f"setDefaultNullStreamAllDevices() 調用失敗: {e}")
                    try:
                        # 嘗試傳遞 True 參數
                        gpu_resource.setDefaultNullStreamAllDevices(True)
                        self.logger.info("setDefaultNullStreamAllDevices(True) 調用成功")
                    except TypeError as e2:
                        self.logger.error(f"setDefaultNullStreamAllDevices(True) 也失敗: {e2}")
                        raise e2
                except Exception as e:
                    asyncio.create_task(func.report_error(e, "setDefaultNullStreamAllDevices call"))
                    raise e

                self._gpu_resource = gpu_resource
                self._fallback_mode = False  # 重置降級模式
                self._recovery_attempts = 0   # 重置恢復嘗試次數

                self.logger.info(f"GPU 資源建立成功，記憶體限制: {self.max_memory_mb}MB，暫存: {temp_memory_mb}MB")
                return self._gpu_resource

            except Exception as e:
                asyncio.create_task(func.report_error(e, "GPU resource creation"))
                self.logger.error(f"建立 GPU 資源失敗: {e}")
                self._gpu_resource = None
                self._fallback_mode = True
                self._recovery_attempts += 1

                # 嘗試清理 GPU 記憶體後重試
                if self._recovery_attempts <= self._max_recovery_attempts:
                    self.logger.info(f"嘗試清理 GPU 記憶體後重新建立資源 (嘗試 {self._recovery_attempts}/{self._max_recovery_attempts})")
                    try:
                        self.clear_gpu_memory()
                        time.sleep(0.5)  # 短暫等待
                        return self.get_gpu_resource()  # 遞迴重試
                    except Exception as retry_error:
                        self.logger.warning(f"GPU 資源恢復嘗試失敗: {retry_error}")

                return None
    
    def clear_gpu_memory(self) -> None:
        """清除 GPU 記憶體"""
        try:
            # 清除 PyTorch 快取
            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            
            # 重置 FAISS GPU 資源
            with self._memory_lock:
                if self._gpu_resource is not None:
                    # 不直接刪除，讓 FAISS 自行管理
                    self._gpu_resource = None
            
            # 強制垃圾回收
            gc.collect()
            
            self.logger.debug("GPU 記憶體清理完成")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "GPU memory cleanup"))
    
    def _trigger_memory_cleanup(self) -> None:
        """主動觸發記憶體清理機制"""
        try:
            self.logger.info("觸發主動記憶體清理")
            
            # 清除 PyTorch GPU 快取
            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            
            # 強制垃圾回收
            gc.collect()
            
            # 記錄清理後的記憶體狀態
            total_mb, free_mb, used_percent = self.get_gpu_memory_info()
            self.logger.info(f"記憶體清理後狀態: 總計 {total_mb}MB, 可用 {free_mb}MB, 使用率 {used_percent:.1f}%")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "GPU memory cleanup trigger"))
    
    def force_cleanup_fallback(self) -> bool:
        """強制清理fallback機制"""
        try:
            self.logger.warning("執行強制記憶體清理fallback")
            
            # 重置GPU資源
            with self._memory_lock:
                self._gpu_resource = None
            
            # 多次清理GPU快取
            if TORCH_AVAILABLE and torch.cuda.is_available():
                for _ in range(3):
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    gc.collect()
            
            # 檢查清理效果
            _, _, used_percent = self.get_gpu_memory_info()
            success = used_percent < 70.0
            
            if success:
                self.logger.info(f"強制清理成功，使用率降至 {used_percent:.1f}%")
            else:
                self.logger.warning(f"強制清理後使用率仍為 {used_percent:.1f}%")
            
            return success
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "force cleanup fallback"))
            return False
    
    def log_memory_stats(self, force_log: bool = False) -> None:
        """記錄記憶體統計資訊"""
        try:
            total_mb, free_mb, used_percent = self.get_gpu_memory_info()
            if total_mb > 0:
                # 嘗試使用啟動日誌管理器
                startup_logger = get_startup_logger()
                if startup_logger and startup_logger.is_startup_mode:
                    startup_logger.log_gpu_memory_check(
                        total_mb, free_mb, used_percent, force_log
                    )
                else:
                    # 正常模式或無啟動日誌管理器時使用原始日誌
                    self.logger.info(
                        f"GPU 記憶體狀態: 總計 {total_mb}MB, "
                        f"可用 {free_mb}MB, 使用率 {used_percent:.1f}%"
                    )
        except Exception as e:
            asyncio.create_task(func.report_error(e, "GPU memory stats logging"))


class VectorIndex:
    """向量索引封裝類別
    
    封裝 FAISS 索引的基本操作，提供統一的介面。
    """
    
    def __init__(
        self,
        dimension: int,
        index_type: str = "Flat",
        metric: str = "L2",
        use_gpu: bool = False,
        gpu_memory_manager: Optional[GPUMemoryManager] = None,
        hnsw_m: int = 64
    ):
        """初始化向量索引
        
        Args:
            dimension: 向量維度
            index_type: 索引類型 ("Flat", "IVFFlat", "HNSW" 等)
            metric: 距離度量 ("L2", "IP")
            use_gpu: 是否使用 GPU
            gpu_memory_manager: GPU 記憶體管理器
            hnsw_m: HNSW 索引的 M 參數
        """
        self.dimension = dimension
        self.index_type = index_type
        self.metric = metric
        self.use_gpu = use_gpu
        self.gpu_memory_manager = gpu_memory_manager
        self.hnsw_m = hnsw_m
        self._index: Optional[faiss.Index] = None
        self._gpu_index: Optional[faiss.Index] = None
        self._id_map: Dict[int, str] = {}  # FAISS ID -> 實際 ID 映射
        self._reverse_id_map: Dict[str, int] = {}  # 實際 ID -> FAISS ID 映射
        self._next_id = 0
        self._gpu_fallback_warned = False  # GPU 降級警告標記
        self._needs_mapping_rebuild = False  # 標記是否需要重建映射
        self.logger = logging.getLogger(__name__)
        # 統一的可重入狀態鎖，保護索引與映射之間的原子性
        self._state_lock = threading.RLock()
        # HNSW 延遲刪除標記集合
        self._deleted_marks: Set[str] = set()
    
    def _create_index(self) -> faiss.Index:
        """建立 FAISS 索引
        
        Returns:
            faiss.Index: FAISS 索引實例
        """
        if self.metric == "L2":
            if self.index_type == "Flat":
                index = faiss.IndexFlatL2(self.dimension)
            elif self.index_type == "IVFFlat":
                quantizer = faiss.IndexFlatL2(self.dimension)
                index = faiss.IndexIVFFlat(quantizer, self.dimension, 100)
            elif self.index_type == "HNSW":
                index = faiss.IndexHNSWFlat(self.dimension, self.hnsw_m)
            else:
                self.logger.warning(f"不支援的索引類型: {self.index_type}，使用 Flat")
                index = faiss.IndexFlatL2(self.dimension)
        else:  # IP (內積)
            if self.index_type == "Flat":
                index = faiss.IndexFlatIP(self.dimension)
            else:
                self.logger.warning(f"IP 度量僅支援 Flat 索引，使用 IndexFlatIP")
                index = faiss.IndexFlatIP(self.dimension)
        
        # 如果是 IVF 類型，需要訓練
        if hasattr(index, 'is_trained') and not index.is_trained:
            # 生成隨機訓練資料
            training_data = np.random.random((1000, self.dimension)).astype('float32')
            index.train(training_data)

        # 使用 ID 映射包裹，讓索引支援自訂 ID 與 remove_ids
        try:
            base_type = type(index)
            if hasattr(faiss, 'IndexIDMap2'):
                index = faiss.IndexIDMap2(index)
            else:
                index = faiss.IndexIDMap(index)
            self.logger.debug(f"_create_index: 已包裹 IndexIDMap，base_type={base_type}, wrapped_type={type(index)}")
        except Exception as e:
            asyncio.create_task(func.report_error(e, "IndexIDMap wrapping"))

        return index
    
    def get_index(self) -> faiss.Index:
        """取得索引實例（懶載入）
        
        Returns:
            faiss.Index: 索引實例
        """
        if self._index is None:
            self._index = self._create_index()
            
            # 嘗試移至 GPU（使用記憶體管理器）
            if self.use_gpu and faiss.get_num_gpus() > 0:
                self._try_move_to_gpu()
        
        return self._gpu_index if self._gpu_index is not None else self._index
    
    def _try_move_to_gpu(self) -> bool:
        """嘗試將索引移至 GPU（支援自動恢復）

        Returns:
            bool: 是否成功移至 GPU
        """
        try:
            # 檢查基本條件
            if not gpu_manager.is_gpu_available():
                if not self._gpu_fallback_warned:
                    self.logger.info("GPU 不可用，自動降級到 CPU 模式")
                    self._gpu_fallback_warned = True
                return False

            if not hasattr(faiss, 'StandardGpuResources'):
                if not self._gpu_fallback_warned:
                    self.logger.info("faiss-gpu 不可用，使用 CPU 模式")
                    self._gpu_fallback_warned = True
                return False

            # 取得 GPU 資源
            gpu_resource = self.gpu_memory_manager.get_gpu_resource() if self.gpu_memory_manager else None

            if gpu_resource is None:
                if not self._gpu_fallback_warned:
                    self.logger.warning("無法取得 GPU 資源，降級使用 CPU")
                    self._gpu_fallback_warned = True
                return False

            # 估算索引記憶體需求
            estimated_memory_mb = self._estimate_index_memory()

            # 檢查記憶體是否足夠
            if (self.gpu_memory_manager and
                not self.gpu_memory_manager.is_memory_available(estimated_memory_mb)):
                if not self._gpu_fallback_warned:
                    self.logger.warning(f"GPU 記憶體不足（需要 {estimated_memory_mb}MB），使用 CPU")
                    self._gpu_fallback_warned = True
                return False

            # 移至 GPU
            self._gpu_index = faiss.index_cpu_to_gpu(gpu_resource, 0, self._index)

            # 記錄成功遷移
            startup_logger = get_startup_logger()
            if startup_logger and startup_logger.is_startup_mode:
                startup_logger.log_gpu_index_migration("unknown", estimated_memory_mb)
            else:
                self.logger.info(f"索引已移至 GPU（預估記憶體: {estimated_memory_mb}MB）")

            # 記錄記憶體狀態
            if self.gpu_memory_manager:
                self.gpu_memory_manager.log_memory_stats()

            return True

        except Exception as e:
            asyncio.create_task(func.report_error(e, "index to GPU migration"))
            if not self._gpu_fallback_warned:
                self._gpu_fallback_warned = True

            # 清除可能部分建立的 GPU 索引
            self._gpu_index = None

            # 清理 GPU 記憶體並嘗試恢復
            if self.gpu_memory_manager:
                try:
                    self.gpu_memory_manager.clear_gpu_memory()
                    # 嘗試恢復 GPU 功能
                    if self.gpu_memory_manager._attempt_gpu_recovery():
                        self.logger.info("GPU 資源已恢復，稍後可重試 GPU 模式")
                except Exception as recovery_error:
                    asyncio.create_task(func.report_error(recovery_error, "GPU recovery after migration failure"))

            return False
    
    def _estimate_index_memory(self) -> int:
        """估算索引的記憶體需求
        
        Returns:
            int: 預估記憶體需求（MB）
        """
        if self._index is None:
            return 0
        
        try:
            # 基本記憶體需求：向量數量 × 維度 × 4 bytes (float32)
            vector_memory_mb = (self._index.ntotal * self.dimension * 4) // (1024 * 1024)
            
            # 索引結構額外開銷（約 20%）
            overhead_mb = max(vector_memory_mb * 0.2, 64)
            
            # FAISS GPU 暫存記憶體需求
            temp_memory_mb = 256
            
            total_mb = int(vector_memory_mb + overhead_mb + temp_memory_mb)
            
            return max(total_mb, 128)  # 最少 128MB
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "index memory estimation"))
            return 512  # 預設值
    
    def add_vectors(self, vectors: np.ndarray, ids: List[str], batch_size: int = 50) -> bool:
        """新增向量到索引（支援批次處理），以統一鎖確保原子性。"""
        try:
            if len(vectors) != len(ids):
                raise ValueError("向量數量與 ID 數量不符")
            vectors = vectors.astype('float32')

            with self._state_lock:
                index = self.get_index()
                ntotal_before = getattr(index, 'ntotal', -1)
                self.logger.debug(f"add_vectors: 取得鎖，索引 ntotal(before)={ntotal_before}, 現有映射數={len(self._id_map)}")

                # 準備暫存對應，不觸碰正式映射與 next_id
                temp_pairs: List[Tuple[int, int]] = []  # (source_vec_idx, temp_faiss_id)
                new_vectors_buf: List[np.ndarray] = []
                new_faiss_ids: List[int] = []

                temp_next_id = self._next_id
                for i, id_str in enumerate(ids):
                    if id_str in self._reverse_id_map:
                        self.logger.debug(f"add_vectors: ID 已存在，跳過 id={id_str}")
                        continue
                    faiss_id = temp_next_id
                    temp_next_id += 1
                    temp_pairs.append((i, faiss_id))
                    new_vectors_buf.append(vectors[i])
                    new_faiss_ids.append(faiss_id)

                if not new_vectors_buf:
                    self.logger.debug("add_vectors: 無需新增，新向量數=0")
                    return True

                new_vectors_arr = np.array(new_vectors_buf, dtype='float32')

                # 在鎖內決定本次寫入目標，並傳遞給批次寫入
                write_target = 'gpu' if self._gpu_index is not None else 'cpu'
                self.logger.debug(f"add_vectors: 決定寫入目標 write_target={write_target}，批次大小={batch_size}，待新增數量={len(new_vectors_arr)}")

                # 先將向量寫入 FAISS 索引
                success = self._add_vectors_batch(new_vectors_arr, new_faiss_ids, batch_size, write_target)
                index = self.get_index()
                ntotal_after_add = getattr(index, 'ntotal', -1)
                self.logger.debug(f"add_vectors: 寫入 FAISS 完成，success={success}，ntotal(after_add)={ntotal_after_add}")

                if not success:
                    self.logger.warning("add_vectors: _add_vectors_batch 失敗，放棄映射更新以保持一致性")
                    return False

                # 僅在成功後一次性更新映射與 next_id
                for (src_idx, faiss_id) in temp_pairs:
                    id_str = ids[src_idx]
                    self._id_map[faiss_id] = id_str
                    self._reverse_id_map[id_str] = faiss_id
                self._next_id = temp_next_id

                self.logger.debug(
                    f"add_vectors: 更新映射完成，新增映射數={len(temp_pairs)}，"
                    f"next_id={self._next_id}，映射總數={len(self._id_map)}，索引 ntotal={getattr(index, 'ntotal', -1)}"
                )
                return True

        except Exception as e:
            asyncio.create_task(func.report_error(e, "vector addition"))
            return False
    
    def _add_vectors_batch(self, vectors: np.ndarray, faiss_ids: List[int], batch_size: int, write_target: str) -> bool:
        """批次新增向量到索引（遵循外部決策的寫入目標）。"""
        try:
            index = self.get_index()
            total_vectors = len(vectors)

            self.logger.debug(f"_add_vectors_batch: ntotal(before)={getattr(index, 'ntotal', -1)}, 批次總數={total_vectors}, 對應暫存ID數={len(faiss_ids)}，write_target={write_target}")

            for i in range(0, total_vectors, batch_size):
                end_idx = min(i + batch_size, total_vectors)
                batch_vectors = vectors[i:end_idx]

                # 嚴格依照寫入目標，避免動態切換導致的非原子性
                batch_ids = np.asarray(faiss_ids[i:end_idx], dtype=np.int64)

                if write_target == 'gpu':
                    if self._gpu_index is None:
                        self.logger.error("_add_vectors_batch: 預期 GPU 寫入但 _gpu_index 為 None")
                        return False
                    index.add_with_ids(batch_vectors, batch_ids)
                elif write_target == 'cpu':
                    if self._index is None:
                        self.logger.error("_add_vectors_batch: 預期 CPU 寫入但 _index 為 None")
                        return False
                    self._index.add_with_ids(batch_vectors, batch_ids)
                else:
                    self.logger.error(f"_add_vectors_batch: 非法 write_target={write_target}")
                    return False

                self.logger.debug(f"_add_vectors_batch: 批次 {i//batch_size + 1}/{(total_vectors + batch_size - 1)//batch_size} 完成")

                # 定期清理記憶體（避免長批次造成壓力）
                if (i + batch_size) % (batch_size * 4) == 0:
                    gc.collect()

            # 追加一次 ntotal 記錄
            index_after = self.get_index()
            self.logger.debug(f"_add_vectors_batch: ntotal(after)={getattr(index_after, 'ntotal', -1)} 成功新增 {total_vectors} 個向量到索引")
            return True

        except Exception as e:
            asyncio.create_task(func.report_error(e, "batch vector addition"))
            return False

    def remove_vectors(self, ids: List[str]) -> int:
        """從索引中移除向量，使用統一鎖確保與映射更新的原子性。"""
        if not ids:
            return 0

        try:
            with self._state_lock:
                index = self.get_index()
                ntotal_before = getattr(index, 'ntotal', -1)

                # 紀錄目前索引型別（GPU/CPU）
                self.logger.debug(
                    f"remove_vectors: active_index_type={type(index)}, "
                    f"cpu_index_type={type(self._index)}, "
                    f"gpu_index_type={type(self._gpu_index) if self._gpu_index is not None else None}"
                )

                # 在鎖內先確定要移除的 FAISS ID 集合（精準且不可變）
                faiss_ids_to_remove = [self._reverse_id_map[id_str] for id_str in ids if id_str in self._reverse_id_map]
                if not faiss_ids_to_remove:
                    self.logger.debug("remove_vectors: 取得鎖後無可移除 ID，直接返回 0")
                    return 0

                self.logger.debug(
                    f"remove_vectors: 取得鎖，ntotal(before)={ntotal_before}，預計移除數={len(faiss_ids_to_remove)}"
                )

                # 將待移除的 FAISS ID 轉為 NumPy int64，符合 FAISS 綁定需求
                ids_to_remove_np = np.asarray(faiss_ids_to_remove, dtype=np.int64)
                if ids_to_remove_np.size == 0:
                    self.logger.debug("remove_vectors: 轉換後無可移除 ID，返回 0")
                    return 0

                # 強制在 CPU IndexIDMap 上執行刪除，避免 GPU/非 IDMap 類型不支援 remove_ids
                target_index = self._index if self._index is not None else index
                try:
                    is_idmap = isinstance(target_index, faiss.IndexIDMap) or (hasattr(faiss, 'IndexIDMap2') and isinstance(target_index, faiss.IndexIDMap2))
                except Exception:
                    is_idmap = False
                if not is_idmap:
                    try:
                        base_type = type(target_index)
                        target_index = faiss.IndexIDMap2(target_index) if hasattr(faiss, 'IndexIDMap2') else faiss.IndexIDMap(target_index)
                        self._index = target_index
                        self.logger.warning(f"remove_vectors: CPU 索引非 IDMap，已於刪除前包裹，base_type={base_type}, wrapped_type={type(target_index)}")
                    except Exception as e:
                        self.logger.error(f"remove_vectors: 嘗試將 CPU 索引包裹為 IDMap 失敗: {e}")
                        return 0

                removed_count_before = getattr(target_index, 'ntotal', -1)
                try:
                    if hasattr(faiss, "IDSelectorArray"):
                        selector = faiss.IDSelectorArray(int(ids_to_remove_np.size), faiss.swig_ptr(ids_to_remove_np))
                        target_index.remove_ids(selector)
                    else:
                        # 後備路徑：直接用 int64 陣列
                        target_index.remove_ids(ids_to_remove_np)
                except Exception as e:
                    self.logger.error(f"remove_vectors: remove_ids 失敗: {e}")
                    return 0

                removed_count_after = getattr(target_index, 'ntotal', -1)
                actually_removed = max(0, removed_count_before - removed_count_after) if removed_count_before != -1 and removed_count_after != -1 else len(ids_to_remove_np)
                self.logger.debug(f"remove_vectors: remove_ids 完成，實際移除數={actually_removed}，target_type={type(target_index)}")

                # 如有 GPU 索引，移除後重新同步 GPU 索引
                if self._gpu_index is not None:
                    try:
                        self.logger.debug("remove_vectors: 偵測到 GPU 索引，將重新同步 GPU 內容")
                        self._gpu_index = None
                        self._try_move_to_gpu()
                        self.logger.debug("remove_vectors: GPU 索引已重新同步")
                    except Exception as e:
                        self.logger.warning(f"remove_vectors: 重新同步 GPU 索引失敗: {e}")

                ntotal_after_local = getattr(self._index, 'ntotal', -1)

            # 移除操作已於鎖內完成；此處不再重複呼叫 remove_ids 以避免型別與狀態競爭問題
            removed_count = len(faiss_ids_to_remove)

            # 無論 removed_count 如何，都移除最初決定的映射
            for id_str in ids:
                if id_str in self._reverse_id_map:
                    faiss_id = self._reverse_id_map.pop(id_str)
                    self._id_map.pop(faiss_id, None)

            if removed_count != len(faiss_ids_to_remove):
                self.logger.warning(
                    f"remove_vectors: remove_ids 實際移除 {removed_count} 與預期 {len(faiss_ids_to_remove)} 不符，標記需要重建映射"
                )
                self._needs_mapping_rebuild = True

            ntotal_after = ntotal_after_local
            self.logger.debug(f"remove_vectors: 完成，ntotal(after)={ntotal_after}，removed_count={removed_count}，映射剩餘={len(self._id_map)}")
            return len(faiss_ids_to_remove)

        except Exception as e:
            asyncio.create_task(func.report_error(e, "vector removal"))
            return 0
    
    def search(
        self,
        query_vector: np.ndarray,
        k: int = 10
    ) -> Tuple[List[float], List[str]]:
        """搜尋相似向量
        
        Args:
            query_vector: 查詢向量
            k: 返回結果數量
            
        Returns:
            Tuple[List[float], List[str]]: (距離列表, ID 列表)
        """
        try:
            # 驗證查詢向量
            if query_vector is None or query_vector.size == 0:
                self.logger.error("查詢向量為空或無效")
                return [], []
            
            # 確保向量維度正確
            if query_vector.shape[0] != self.dimension:
                self.logger.error(
                    f"查詢向量維度不匹配: 期望 {self.dimension}, 實際 {query_vector.shape[0]}"
                )
                return [], []
            
            query_vector = query_vector.astype('float32').reshape(1, -1)
            index = self.get_index()
            
            # 檢查索引狀態
            if not hasattr(index, 'ntotal'):
                self.logger.error("索引物件無效，缺少 ntotal 屬性")
                return [], []
            
            if index.ntotal == 0:
                self.logger.warning("索引為空，沒有可搜尋的向量")
                return [], []
            
            # 檢查索引維度
            if hasattr(index, 'd') and index.d != self.dimension:
                self.logger.error(
                    f"索引維度不匹配: 期望 {self.dimension}, 索引 {index.d}"
                )
                return [], []
            
            # 確保 k 值合理
            search_k = min(k, index.ntotal)
            if search_k <= 0:
                self.logger.warning("搜尋數量無效")
                return [], []
            
            # 執行完整性檢查
            integrity_issues = self._check_index_integrity()
            if integrity_issues:
                self.logger.warning(f"檢測到索引完整性問題: {integrity_issues}")
                # 嘗試自動修復
                if self._attempt_auto_repair():
                    self.logger.info("索引完整性問題已自動修復")
                    # 重新獲取索引
                    index = self.get_index()
                else:
                    self.logger.error("索引完整性問題修復失敗")
            
            self.logger.debug(
                f"開始向量搜尋: 查詢維度={query_vector.shape}, "
                f"索引向量數={index.ntotal}, k={search_k}, "
                f"映射數量={len(self._id_map)}"
            )
            
            # 執行搜尋
            distances, indices = index.search(query_vector, search_k)
            
            # 轉換結果並處理缺失映射
            result_distances = []
            result_ids = []
            missing_mappings = []
            
            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1:  # 無效結果
                    continue
                elif idx in self._id_map:
                    result_distances.append(float(dist))
                    result_ids.append(self._id_map[idx])
                else:
                    # 記錄缺失的映射用於診斷
                    missing_mappings.append(idx)
                    self.logger.warning(
                        f"找到向量索引 {idx} 但無對應的 ID 映射，"
                        f"索引向量總數: {index.ntotal}, 映射總數: {len(self._id_map)}"
                    )
            
            # 如果有大量缺失映射，記錄詳細診斷資訊
            if missing_mappings:
                self._log_mapping_diagnostics(missing_mappings, index)
            
            self.logger.debug(f"向量搜尋完成，返回 {len(result_ids)} 個結果")
            return result_distances, result_ids
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "vector search"))
            return [], []
    
    def get_stats(self) -> Dict[str, Union[int, str, bool]]:
        """取得索引統計資訊
        
        Returns:
            Dict[str, Union[int, str, bool]]: 統計資訊
        """
        index = self.get_index() if self._index is not None else None
        return {
            "total_vectors": index.ntotal if index else 0,
            "dimension": self.dimension,
            "index_type": self.index_type,
            "metric": self.metric,
            "use_gpu": self.use_gpu,
            "is_trained": index.is_trained if hasattr(index, 'is_trained') and index else True
        }

    def get_all_ids(self) -> List[str]:
        """取得此索引中的所有真實 ID"""
        return list(self._reverse_id_map.keys())
    
    async def save(self, file_path: Path) -> bool:
        """非同步儲存索引到檔案（原子性操作）
        
        Args:
            file_path: 儲存路徑
            
        Returns:
            bool: 是否成功
        """
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 以統一鎖快照目前索引狀態，並安全處理 GPU→CPU 儲存
            with self._state_lock:
                active_index = self.get_index()
                was_gpu = (self._gpu_index is not None and id(active_index) == id(self._gpu_index))

                if was_gpu:
                    self.logger.info("save: 偵測到活動索引位於 GPU，建立 CPU 快照以進行序列化")
                    try:
                        cpu_snapshot = faiss.index_gpu_to_cpu(self._gpu_index)
                        self.logger.debug(f"save: GPU→CPU 轉移成功，snapshot_type={type(cpu_snapshot)}，ntotal={getattr(cpu_snapshot, 'ntotal', -1)}")
                    except Exception as e:
                        self.logger.error(f"save: GPU→CPU 轉移失敗，無法儲存: {e}")
                        return False
                    index_to_save = cpu_snapshot
                else:
                    index_to_save = active_index

                if index_to_save is None:
                    self.logger.error("沒有可用的索引進行儲存")
                    return False

            # 使用原子性操作儲存檔案（確保不改變活動索引狀態）
            return await self._atomic_save(file_path, index_to_save, was_gpu=was_gpu)
            
        except Exception as e:
            await func.report_error(e, f"index save to {file_path}")
            return False

    async def _atomic_save(self, file_path: Path, index: faiss.Index, was_gpu: bool = False) -> bool:
        """原子性儲存索引和映射檔案
        
        Args:
            file_path: 目標檔案路徑
            index: 要儲存的索引
            
        Returns:
            bool: 是否成功
        """
        try:
            # 使用臨時檔案進行原子性寫入
            with tempfile.TemporaryDirectory(prefix="vector_save_") as temp_dir:
                temp_dir_path = Path(temp_dir)
                
                # 臨時檔案路徑
                temp_index_path = temp_dir_path / f"{file_path.name}.tmp"
                temp_mapping_path = temp_dir_path / f"{file_path.name}.mapping.tmp"
                
                # 準備要寫入之 CPU 索引（若為 GPU 索引則先轉為 CPU 快照）
                cpu_index = index
                gpu_detected = False
                try:
                    # 基於型別名稱進行輕量偵測，避免誤判；save() 已先嘗試處理 GPU→CPU
                    if 'Gpu' in type(index).__name__:
                        gpu_detected = True
                        self.logger.info("atomic_save: 偵測到 GPU 索引，開始執行 GPU→CPU 轉移以便序列化")
                        cpu_index = faiss.index_gpu_to_cpu(index)
                        self.logger.debug(f"atomic_save: GPU→CPU 轉移成功，snapshot_type={type(cpu_index)}，ntotal={getattr(cpu_index, 'ntotal', -1)}")
                except Exception as conv_e:
                    self.logger.error(f"atomic_save: GPU→CPU 轉移失敗: {conv_e}")
                    return False

                # 儲存索引到臨時檔案
                self.logger.debug(f"儲存索引到臨時檔案: {temp_index_path} | source={'GPU' if (gpu_detected or was_gpu) else 'CPU'}")
                faiss.write_index(cpu_index, str(temp_index_path))
                
                # 儲存映射到臨時檔案
                mapping_data = {
                    'id_map': self._id_map,
                    'reverse_id_map': self._reverse_id_map,
                    'next_id': self._next_id,
                    'dimension': self.dimension,
                    'index_type': self.index_type,
                    'metric': self.metric,
                    'timestamp': time.time(),  # 添加時間戳
                    'checksum': self._calculate_mapping_checksum()  # 添加校驗和
                }
                
                self.logger.debug(f"儲存映射到臨時檔案: {temp_mapping_path}")
                with open(temp_mapping_path, 'wb') as f:
                    pickle.dump(mapping_data, f)
                
                # 驗證臨時檔案
                if not self._validate_saved_files(temp_index_path, temp_mapping_path, cpu_index):
                    self.logger.error("臨時檔案驗證失敗")
                    return False
                
                # 原子性移動檔案到最終位置
                final_mapping_path = file_path.with_suffix('.mapping')
                
                # 如果目標檔案存在，先備份
                backup_paths = []
                if file_path.exists():
                    backup_index = file_path.with_suffix(f'.backup_{int(time.time())}')
                    shutil.move(str(file_path), str(backup_index))
                    backup_paths.append(backup_index)
                    self.logger.debug(f"備份舊索引檔案: {backup_index}")
                
                if final_mapping_path.exists():
                    backup_mapping = final_mapping_path.with_suffix(f'.backup_{int(time.time())}')
                    shutil.move(str(final_mapping_path), str(backup_mapping))
                    backup_paths.append(backup_mapping)
                    self.logger.debug(f"備份舊映射檔案: {backup_mapping}")
                
                try:
                    # 原子性移動檔案
                    shutil.move(str(temp_index_path), str(file_path))
                    shutil.move(str(temp_mapping_path), str(final_mapping_path))
                    
                    # 驗證最終檔案
                    file_size = file_path.stat().st_size
                    vector_count = index.ntotal
                    mapping_size = len(self._id_map)
                    
                    self.logger.debug(
                        f"索引已原子性儲存到: {file_path} "
                        f"(檔案大小: {file_size} bytes, 向量數量: {vector_count}, 映射數量: {mapping_size})"
                    )
                    
                    # 檢查檔案完整性
                    if file_size <= 45 and vector_count > 0:
                        self.logger.warning(
                            f"索引檔案大小異常小 ({file_size} bytes)，"
                            f"但索引包含 {vector_count} 個向量"
                        )
                    
                    # 清理備份檔案（保留最近的幾個）
                    self._cleanup_old_backups(file_path, max_backups=3)
                    
                    return True
                    
                except Exception as e:
                    # 恢復備份檔案
                    self.logger.error(f"原子性移動失敗，恢復備份: {e}")
                    for backup_path in backup_paths:
                        if backup_path.name.endswith('.backup_' + str(int(time.time()))):
                            if 'mapping' in backup_path.name:
                                shutil.move(str(backup_path), str(final_mapping_path))
                            else:
                                shutil.move(str(backup_path), str(file_path))
                    raise
                    
        except Exception as e:
            await func.report_error(e, f"atomic index save to {file_path}")
            return False
    
    def _calculate_mapping_checksum(self) -> str:
        """計算映射資料的校驗和
        
        Returns:
            str: 校驗和字串
        """
        try:
            import hashlib
            
            # 建立可重現的字串表示
            data_str = f"{len(self._id_map)},{len(self._reverse_id_map)},{self._next_id}"
            
            # 添加映射內容的摘要
            if self._id_map:
                sorted_items = sorted(self._id_map.items())
                for faiss_id, real_id in sorted_items[:10]:  # 只取前10個避免過大
                    data_str += f",{faiss_id}:{real_id}"
            
            return hashlib.md5(data_str.encode()).hexdigest()
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "mapping checksum calculation"))
            return "unknown"
    
    def _validate_saved_files(self, index_path: Path, mapping_path: Path, original_index: faiss.Index) -> bool:
        """驗證儲存的檔案
        
        Args:
            index_path: 索引檔案路徑
            mapping_path: 映射檔案路徑
            original_index: 原始索引
            
        Returns:
            bool: 是否驗證通過
        """
        try:
            # 檢查檔案是否存在
            if not index_path.exists() or not mapping_path.exists():
                self.logger.error("儲存的檔案不存在")
                return False
            
            # 檢查索引檔案大小
            index_size = index_path.stat().st_size
            if index_size == 0:
                self.logger.error("索引檔案為空")
                return False
            
            # 嘗試載入索引進行驗證
            try:
                test_index = faiss.read_index(str(index_path))
                if test_index.ntotal != original_index.ntotal:
                    self.logger.error(f"索引大小不匹配: 期望 {original_index.ntotal}, 實際 {test_index.ntotal}")
                    return False
            except Exception as e:
                self.logger.error(f"無法載入儲存的索引進行驗證: {e}")
                return False
            
            # 檢查映射檔案
            try:
                with open(mapping_path, 'rb') as f:
                    mapping_data = pickle.load(f)
                
                required_keys = ['id_map', 'reverse_id_map', 'next_id']
                for key in required_keys:
                    if key not in mapping_data:
                        self.logger.error(f"映射檔案缺少必要鍵: {key}")
                        return False
                
                # 驗證映射大小
                if len(mapping_data['id_map']) != len(self._id_map):
                    self.logger.error("映射大小不匹配")
                    return False
                    
            except Exception as e:
                self.logger.error(f"無法載入儲存的映射進行驗證: {e}")
                return False
            
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "saved file validation"))
            return False
    
    def _cleanup_old_backups(self, file_path: Path, max_backups: int = 3) -> None:
        """清理舊的備份檔案
        
        Args:
            file_path: 主檔案路徑
            max_backups: 保留的最大備份數量
        """
        try:
            # 尋找備份檔案
            backup_pattern = f"{file_path.stem}.backup_*"
            backup_files = list(file_path.parent.glob(backup_pattern))
            
            # 按修改時間排序（最新的在前）
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # 刪除超過限制的舊備份
            for old_backup in backup_files[max_backups:]:
                try:
                    old_backup.unlink()
                    self.logger.debug(f"已刪除舊備份: {old_backup}")
                except Exception as e:
                    self.logger.warning(f"刪除舊備份失敗: {old_backup}, {e}")
                    
        except Exception as e:
            asyncio.create_task(func.report_error(e, "old backup cleanup"))
    
    def load(self, file_path: Path) -> bool:
        """從檔案載入索引（帶完整性檢查）
        
        Args:
            file_path: 索引檔案路徑
            
        Returns:
            bool: 是否成功
        """
        try:
            if not file_path.exists():
                self.logger.warning(f"索引檔案不存在: {file_path}")
                return False
            
            # 載入前先記錄狀態
            self.logger.debug(f"開始載入索引檔案: {file_path}")
            
            # 載入 FAISS 索引
            temp_index = faiss.read_index(str(file_path))
            self.logger.debug(f"load: 讀取索引完成，loaded_type={type(temp_index)}")

            # 確保索引使用 ID 映射包裹（避免某些索引不支援 remove_ids）
            try:
                is_idmap = isinstance(temp_index, faiss.IndexIDMap) or (hasattr(faiss, 'IndexIDMap2') and isinstance(temp_index, faiss.IndexIDMap2))
            except Exception as e:
                asyncio.create_task(func.report_error(e, "is_idmap check failure"))
                is_idmap = False

            # 注意：FAISS 要求在包裹 IndexIDMap 前索引必須為空(ntotal==0)；否則需重建
            try:
                loaded_ntotal = getattr(temp_index, 'ntotal', 0)
            except Exception as e:
                asyncio.create_task(func.report_error(e, "loaded_ntotal check failure"))
                loaded_ntotal = 0

            if not is_idmap:
                if loaded_ntotal == 0:
                    # 空索引可安全直接包裹
                    try:
                        base_type = type(temp_index)
                        temp_index = faiss.IndexIDMap2(temp_index) if hasattr(faiss, 'IndexIDMap2') else faiss.IndexIDMap(temp_index)
                        self.logger.debug(f"load: 空索引直接包裹為 IndexIDMap，base_type={base_type}, wrapped_type={type(temp_index)}")
                    except Exception as e:
                        asyncio.create_task(func.report_error(e, "IndexIDMap wrapping for empty index"))
                        self.logger.warning(f"load: 空索引包裹 IndexIDMap 失敗: {e}; current_type={type(temp_index)}")
                else:
                    # 非空且非 IDMap，執行重建流程
                    self.logger.info(f"load: 偵測到非 IDMap 且非空索引，開始重建以支援 remove_ids | type={type(temp_index)}, ntotal={loaded_ntotal}")
                    try:
                        # a) 從舊索引提取所有向量
                        self.logger.debug("load: 重建-開始提取舊索引向量")
                        vectors = np.empty((loaded_ntotal, self.dimension), dtype='float32')
                        for i in range(loaded_ntotal):
                            try:
                                vec = temp_index.reconstruct(i)
                                vectors[i] = np.asarray(vec, dtype='float32')
                            except Exception as re_e:
                                self.logger.error(f"load: reconstruct 失敗於 i={i}: {re_e}")
                                raise
                        self.logger.debug(f"load: 重建-向量提取完成，共 {loaded_ntotal} 條")

                        # b) 建立全新的空索引並包裹為 IndexIDMap
                        self.logger.debug("load: 重建-建立新的空索引(含 IDMap 包裹)")
                        new_index = self._create_index()  # 內部已包裹 IndexIDMap/IndexIDMap2

                        # c) 以舊索引的隱含 ID(0..ntotal-1) 回填向量
                        self.logger.debug("load: 重建-回填向量至新索引")
                        new_ids = np.arange(loaded_ntotal, dtype=np.int64)
                        new_index.add_with_ids(vectors, new_ids)

                        # d) 用重建後的新索引替換
                        temp_index = new_index

                        # e) 詳細日誌
                        self.logger.info(f"load: 重建完成並替換索引，new_ntotal={getattr(temp_index, 'ntotal', -1)}, wrapped_type={type(temp_index)}")
                    except Exception as rb_e:
                        asyncio.create_task(func.report_error(rb_e, "Index reconstruction failure"))
                        self.logger.error(f"load: 索引重建失敗，無法保證 remove_ids 功能: {rb_e}")
                        raise
            else:
                self.logger.debug(f"load: 索引已為 IDMap，type={type(temp_index)}")
            
            # 載入 ID 映射
            mapping_path = file_path.with_suffix('.mapping')
            temp_id_map = {}
            temp_reverse_id_map = {}
            temp_next_id = 0
            mapping_checksum = None
            
            if mapping_path.exists():
                self.logger.debug(f"載入映射檔案: {mapping_path}")
                try:
                    with open(mapping_path, 'rb') as f:
                        data = pickle.load(f)
                        temp_id_map = data.get('id_map', {})
                        temp_reverse_id_map = data.get('reverse_id_map', {})
                        temp_next_id = data.get('next_id', 0)
                        mapping_checksum = data.get('checksum')
                        
                        # 檢查維度相容性
                        if 'dimension' in data and data['dimension'] != self.dimension:
                            self.logger.warning(
                                f"映射檔案維度({data['dimension']})與當前配置({self.dimension})不匹配"
                            )
                except Exception as e:
                    asyncio.create_task(func.report_error(e, "Mapping file loading failure"))
                    self.logger.error(f"載入映射檔案失敗: {e}")
                    # 繼續載入但使用空映射
                    temp_id_map = {}
                    temp_reverse_id_map = {}
                    temp_next_id = 0
            else:
                self.logger.warning(f"映射檔案不存在: {mapping_path}")
            
            # 載入後先進行「ID 範圍」健全性檢查與預清理（避免映射含超出 ntotal 的 FAISS ID）
            needs_writeback = False
            try:
                index_size_for_mapping = getattr(temp_index, 'ntotal', 0)
                if temp_id_map:
                    # 找出不合法或超出範圍的 FAISS ID
                    out_of_range_ids = [
                        k for k in temp_id_map.keys()
                        if not isinstance(k, int) or k < 0 or k >= index_size_for_mapping
                    ]
                    max_faiss_id_local = max([k for k in temp_id_map.keys() if isinstance(k, int)], default=-1)
                    if out_of_range_ids or (max_faiss_id_local >= index_size_for_mapping and index_size_for_mapping > 0):
                        self.logger.warning(
                            f"偵測到映射中存在超出索引範圍的 FAISS ID，index.ntotal={index_size_for_mapping}，"
                            f"最大ID={max_faiss_id_local}，將執行清理程序"
                        )
                        cleaned_id_map, cleaned_reverse_map, invalid_ids = self._remove_out_of_range_mappings(
                            index_size_for_mapping, temp_id_map, temp_reverse_id_map
                        )
                        if invalid_ids:
                            preview = invalid_ids[:10]
                            suffix = "..." if len(invalid_ids) > 10 else ""
                            self.logger.warning(f"已移除 {len(invalid_ids)} 個無效映射（示例前10個）: {preview}{suffix}")
                        temp_id_map = cleaned_id_map
                        temp_reverse_id_map = cleaned_reverse_map
                        temp_next_id = max(temp_id_map.keys()) + 1 if temp_id_map else 0
                        needs_writeback = True
            except Exception as e:
                asyncio.create_task(func.report_error(e, "Pre-load mapping cleanup failure"))
                self.logger.warning(f"預載入映射清理時發生錯誤: {e}")
            # 執行載入前的完整性檢查
            load_validation_result = self._validate_loaded_data(
                temp_index, temp_id_map, temp_reverse_id_map, temp_next_id, mapping_checksum
            )
            
            if not load_validation_result['valid']:
                self.logger.warning(f"載入檔案完整性檢查失敗: {load_validation_result['issues']}")
                
                # 嘗試自動修復
                if load_validation_result['repairable']:
                    self.logger.info("嘗試自動修復載入的資料")
                    repaired_data = self._repair_loaded_data(
                        temp_index, temp_id_map, temp_reverse_id_map, temp_next_id
                    )
                    if repaired_data:
                        temp_id_map = repaired_data['id_map']
                        temp_reverse_id_map = repaired_data['reverse_id_map']
                        temp_next_id = repaired_data['next_id']
                        needs_writeback = True
                        self.logger.info("載入資料自動修復成功")
                    else:
                        self.logger.error("載入資料自動修復失敗")
                        return False
                else:
                    self.logger.error("載入資料無法自動修復，建議重建索引")
                    return False
            
            # 將載入的資料設定到實例
            self._index = temp_index
            self._id_map = temp_id_map
            self._reverse_id_map = temp_reverse_id_map
            self._next_id = temp_next_id
            
            # 檢查是否使用了佔位符映射
            placeholder_count = sum(1 for real_id in self._reverse_id_map.keys()
                                  if real_id.startswith('missing_'))
            
            if placeholder_count > 0:
                self.logger.warning(f"檢測到 {placeholder_count} 個佔位符映射，嘗試從資料庫重建真實映射")
                # 這裡我們需要知道頻道 ID 來重建映射，但在 VectorIndex 層級我們沒有這個資訊
                # 所以我們標記這個索引需要後續重建
                self._needs_mapping_rebuild = True
            
            # 執行載入後的完整性檢查
            post_load_issues = self._check_index_integrity()
            if post_load_issues:
                self.logger.warning(f"載入後檢測到完整性問題: {post_load_issues}")
                
                # 嘗試自動修復
                if self._attempt_auto_repair():
                    self.logger.info("載入後完整性問題已自動修復")
                    needs_writeback = True
                else:
                    self.logger.warning("載入後完整性問題修復失敗，但繼續使用")
            
            # 若在載入過程中有對映射進行清理/修復，將清理後的映射原子性寫回磁碟
            if needs_writeback:
                if not self._atomic_write_mapping(mapping_path, self._id_map, self._reverse_id_map, self._next_id):
                    self.logger.warning(f"寫回映射檔案失敗: {mapping_path}")
                else:
                    self.logger.debug(f"已將清理後的映射原子性寫回: {mapping_path}")
            
            # 記錄載入結果
            index_size = self._index.ntotal if self._index else 0
            mapping_size = len(self._id_map)
            self.logger.debug(
                f"索引載入完成 - 向量數量: {index_size}, 映射數量: {mapping_size}, "
                f"完整性: {'正常' if not post_load_issues else '有問題但已處理'}"
            )
            
            # 嘗試移至 GPU（使用優化的記憶體管理）
            if self.use_gpu and faiss.get_num_gpus() > 0:
                self._try_move_to_gpu()
            
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"index load from {file_path}"))
            # 清理可能部分載入的資料
            self._index = None
            self._gpu_index = None
            self._id_map.clear()
            self._reverse_id_map.clear()
            self._next_id = 0
            return False
    
    def _validate_loaded_data(
        self,
        index: faiss.Index,
        id_map: Dict[int, str],
        reverse_id_map: Dict[str, int],
        next_id: int,
        checksum: Optional[str]
    ) -> Dict[str, any]:
        """驗證載入的資料完整性
        
        Args:
            index: 載入的索引
            id_map: 載入的 ID 映射
            reverse_id_map: 載入的反向映射
            next_id: 載入的下一個 ID
            checksum: 載入的校驗和
            
        Returns:
            Dict[str, any]: 驗證結果
        """
        result = {
            'valid': True,
            'issues': [],
            'repairable': True
        }
        
        try:
            # 檢查索引基本屬性
            if not hasattr(index, 'ntotal'):
                result['issues'].append("索引缺少 ntotal 屬性")
                result['valid'] = False
                result['repairable'] = False
                return result
            
            # 檢查維度匹配
            if hasattr(index, 'd') and index.d != self.dimension:
                result['issues'].append(f"索引維度不匹配: 期望 {self.dimension}, 實際 {index.d}")
                result['valid'] = False
                result['repairable'] = False
                return result
            
            index_size = index.ntotal
            mapping_size = len(id_map)
            reverse_mapping_size = len(reverse_id_map)
            
            # 檢查大小匹配
            if index_size != mapping_size:
                result['issues'].append(f"索引大小({index_size})與映射數量({mapping_size})不匹配")
                result['valid'] = False
                # 這種情況可以嘗試修復
            
            if mapping_size != reverse_mapping_size:
                result['issues'].append(f"正向映射({mapping_size})與反向映射({reverse_mapping_size})不匹配")
                result['valid'] = False
                # 這種情況可以嘗試修復
            
            # 檢查映射完整性
            mapping_issues = 0
            for faiss_id, real_id in id_map.items():
                if real_id not in reverse_id_map:
                    mapping_issues += 1
                elif reverse_id_map[real_id] != faiss_id:
                    mapping_issues += 1
                
                # 不檢查所有映射，避免載入時間過長
                if mapping_issues > 10:
                    break
            
            if mapping_issues > 0:
                result['issues'].append(f"檢測到 {mapping_issues}+ 個映射不一致問題")
                result['valid'] = False
            
            # 檢查 next_id 合理性
            if id_map and next_id <= max(id_map.keys()):
                result['issues'].append(f"next_id({next_id})不合理")
                result['valid'] = False
            
            # 驗證校驗和（如果有）
            if checksum and checksum != "unknown":
                current_checksum = self._calculate_temp_checksum(id_map, reverse_id_map, next_id)
                if current_checksum != checksum:
                    result['issues'].append("映射校驗和不匹配")
                    result['valid'] = False
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "loaded data validation"))
            result['issues'].append(f"驗證過程中發生錯誤: {e}")
            result['valid'] = False
            result['repairable'] = False
        
        return result
    
    def _calculate_temp_checksum(self, id_map: Dict[int, str], reverse_id_map: Dict[str, int], next_id: int) -> str:
        """計算臨時映射資料的校驗和
        
        Args:
            id_map: ID 映射
            reverse_id_map: 反向映射
            next_id: 下一個 ID
            
        Returns:
            str: 校驗和
        """
        try:
            import hashlib
            
            data_str = f"{len(id_map)},{len(reverse_id_map)},{next_id}"
            
            if id_map:
                sorted_items = sorted(id_map.items())
                for faiss_id, real_id in sorted_items[:10]:
                    data_str += f",{faiss_id}:{real_id}"
            
            return hashlib.md5(data_str.encode()).hexdigest()
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "temporary checksum calculation"))
            return "unknown"
    
    def _repair_loaded_data(
        self,
        index: faiss.Index,
        id_map: Dict[int, str],
        reverse_id_map: Dict[str, int],
        next_id: int
    ) -> Optional[Dict[str, any]]:
        """修復載入的資料
        
        Args:
            index: 索引
            id_map: ID 映射
            reverse_id_map: 反向映射
            next_id: 下一個 ID
            
        Returns:
            Optional[Dict[str, any]]: 修復後的資料或 None
        """
        try:
            index_size = index.ntotal
            mapping_size = len(id_map)
            
            # 修復大小不匹配
            if index_size != mapping_size:
                if index_size > mapping_size:
                    # 索引更大，嘗試重建映射
                    if mapping_size == 0:
                        # 映射完全遺失，創建佔位符映射
                        self.logger.warning(f"映射完全遺失，為 {index_size} 個向量創建佔位符映射")
                        new_id_map = {}
                        new_reverse_map = {}
                        
                        # 創建佔位符 ID：使用時間戳和索引
                        import time
                        timestamp = int(time.time())
                        
                        for i in range(index_size):
                            placeholder_id = f"missing_{timestamp}_{i}"
                            new_id_map[i] = placeholder_id
                            new_reverse_map[placeholder_id] = i
                        
                        id_map = new_id_map
                        reverse_id_map = new_reverse_map
                        
                        self.logger.info(f"已創建 {len(new_id_map)} 個佔位符映射，索引可正常使用")
                    else:
                        # 部分映射遺失，保留現有映射但警告
                        self.logger.warning(f"部分映射遺失：索引 {index_size} vs 映射 {mapping_size}")
                        # 為缺失的索引項創建佔位符
                        import time
                        timestamp = int(time.time())
                        
                        # 找出已使用的 FAISS ID
                        used_faiss_ids = set(id_map.keys())
                        
                        # 為缺失的 FAISS ID 創建佔位符
                        for i in range(index_size):
                            if i not in used_faiss_ids:
                                placeholder_id = f"missing_{timestamp}_{i}"
                                id_map[i] = placeholder_id
                                reverse_id_map[placeholder_id] = i
                        
                        self.logger.info(f"已為 {index_size - mapping_size} 個缺失映射創建佔位符")
                else:
                    # 映射更大，清理多餘的映射
                    sorted_ids = sorted(id_map.keys())
                    valid_ids = sorted_ids[:index_size]
                    
                    new_id_map = {}
                    new_reverse_map = {}
                    
                    for faiss_id in valid_ids:
                        if faiss_id in id_map:
                            real_id = id_map[faiss_id]
                            new_id_map[faiss_id] = real_id
                            new_reverse_map[real_id] = faiss_id
                    
                    id_map = new_id_map
                    reverse_id_map = new_reverse_map
                    
                    self.logger.info(f"已清理多餘映射，保留 {len(new_id_map)} 個有效映射")
            
            # 修復映射不一致
            corrected_reverse_map = {}
            for faiss_id, real_id in id_map.items():
                corrected_reverse_map[real_id] = faiss_id
            
            # 修復 next_id
            corrected_next_id = max(id_map.keys()) + 1 if id_map else 0
            
            return {
                'id_map': id_map,
                'reverse_id_map': corrected_reverse_map,
                'next_id': corrected_next_id
            }
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "loaded data repair"))
            return None
    
    def _atomic_write_mapping(self, mapping_path: Path, id_map: Dict[int, str], reverse_id_map: Dict[str, int], next_id: int) -> bool:
        """原子性寫入映射檔案（僅更新 .mapping）"""
        try:
            mapping_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = mapping_path.with_name(mapping_path.name + ".tmp")

            mapping_data = {
                'id_map': id_map,
                'reverse_id_map': reverse_id_map,
                'next_id': next_id,
                'checksum': self._calculate_temp_checksum(id_map, reverse_id_map, next_id),
                'dimension': self.dimension,
            }

            with open(tmp_path, 'wb') as f:
                pickle.dump(mapping_data, f)

            os.replace(str(tmp_path), str(mapping_path))
            self.logger.debug(f"atomic_write_mapping: 已原子性覆寫映射至 {mapping_path}")
            return True
        except Exception as e:
            asyncio.create_task(func.report_error(e, "atomic mapping write"))
            try:
                if 'tmp_path' in locals() and Path(tmp_path).exists():
                    Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
            return False

    def _remove_out_of_range_mappings(
        self,
        index_size: int,
        id_map: Dict[int, str],
        reverse_id_map: Dict[str, int]
    ) -> Tuple[Dict[int, str], Dict[str, int], List[int]]:
        """移除超出索引範圍的 FAISS ID 映射，回傳清理後映射與被移除 ID 列表"""
        try:
            invalid_ids: List[int] = [
                fid for fid in id_map.keys()
                if not isinstance(fid, int) or fid < 0 or fid >= index_size
            ]
            if not invalid_ids:
                # 仍確保反向映射與正向一致
                corrected_reverse: Dict[str, int] = {}
                for faiss_id, real_id in id_map.items():
                    corrected_reverse[real_id] = faiss_id
                return id_map, corrected_reverse if corrected_reverse else reverse_id_map, []

            new_id_map: Dict[int, str] = {}
            new_reverse_map: Dict[str, int] = {}
            for faiss_id, real_id in id_map.items():
                if isinstance(faiss_id, int) and 0 <= faiss_id < index_size:
                    new_id_map[faiss_id] = real_id
                    new_reverse_map[real_id] = faiss_id

            return new_id_map, new_reverse_map, sorted(invalid_ids)
        except Exception as e:
            asyncio.create_task(func.report_error(e, "out of range mapping removal"))
            # 發生例外時回傳原資料，避免在載入流程中進一步破壞狀態
            return id_map, reverse_id_map, []
    def clear_gpu_resources(self) -> None:
        """清除 GPU 資源"""
        try:
            # 清除 GPU 索引
            if self._gpu_index is not None:
                self._gpu_index = None
            
            # 清理 GPU 記憶體
            if self.gpu_memory_manager is not None:
                self.gpu_memory_manager.clear_gpu_memory()
            
            self.logger.debug("GPU 資源已清除")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "GPU resource cleanup"))
    
    def _check_index_integrity(self) -> List[str]:
        """檢查索引與映射的完整性
        
        Returns:
            List[str]: 發現的問題列表
        """
        issues = []
        
        try:
            # 檢查索引是否存在
            if self._index is None and self._gpu_index is None:
                issues.append("索引物件不存在")
                return issues
            
            # 獲取當前索引
            current_index = self._gpu_index if self._gpu_index is not None else self._index
            if current_index is None:
                issues.append("無法獲取有效索引")
                return issues
            
            # 檢查索引大小與映射數量是否匹配
            index_size = current_index.ntotal
            mapping_size = len(self._id_map)
            reverse_mapping_size = len(self._reverse_id_map)
            
            if index_size != mapping_size:
                issues.append(f"索引大小({index_size})與 ID 映射數量({mapping_size})不匹配")
            
            if mapping_size != reverse_mapping_size:
                issues.append(f"正向映射({mapping_size})與反向映射({reverse_mapping_size})數量不匹配")
            
            # 檢查映射的 ID 範圍是否有效
            if self._id_map:
                max_faiss_id = max(self._id_map.keys())
                if max_faiss_id >= index_size:
                    issues.append(f"最大 FAISS ID({max_faiss_id})超出索引範圍({index_size})")
            
            # 檢查映射一致性
            for faiss_id, real_id in self._id_map.items():
                if real_id not in self._reverse_id_map:
                    issues.append(f"正向映射 {faiss_id}->{real_id} 在反向映射中不存在")
                elif self._reverse_id_map[real_id] != faiss_id:
                    issues.append(f"映射不一致: {faiss_id}->{real_id}, 但反向映射為 {self._reverse_id_map[real_id]}")
            
            # 檢查 next_id 是否合理
            if self._id_map and self._next_id <= max(self._id_map.keys()):
                issues.append(f"next_id({self._next_id})小於等於最大現有 ID({max(self._id_map.keys())})")
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, "index integrity check"))
            issues.append(f"完整性檢查過程中發生錯誤: {e}")
        
        return issues
    
    def _attempt_auto_repair(self) -> bool:
        """嘗試自動修復索引映射不匹配問題
        
        Returns:
            bool: 是否修復成功
        """
        try:
            self.logger.info("開始自動修復索引映射問題")
            
            # 獲取當前索引
            current_index = self._gpu_index if self._gpu_index is not None else self._index
            if current_index is None:
                self.logger.error("無法獲取索引進行修復")
                return False
            
            index_size = current_index.ntotal
            mapping_size = len(self._id_map)
            
            # 情況 1: 索引比映射大（可能是映射丟失）
            if index_size > mapping_size:
                self.logger.warning(f"索引大小({index_size})大於映射數量({mapping_size})，嘗試清理多餘索引")
                return self._repair_oversized_index(current_index, mapping_size)
            
            # 情況 2: 映射比索引大（可能是索引部分丟失）
            elif mapping_size > index_size:
                self.logger.warning(f"映射數量({mapping_size})大於索引大小({index_size})，嘗試清理多餘映射")
                return self._repair_oversized_mapping(index_size)
            
            # 情況 3: 大小相等但 ID 範圍不匹配
            else:
                self.logger.info("索引與映射大小相等，檢查 ID 範圍")
                return self._repair_id_range_mismatch()
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, "index auto-repair"))
            return False
    
    def _repair_oversized_index(self, index: faiss.Index, target_size: int) -> bool:
        """修復索引過大的問題
        
        Args:
            index: 當前索引
            target_size: 目標大小
            
        Returns:
            bool: 是否修復成功
        """
        try:
            # 如果映射為空，清空整個索引
            if target_size == 0:
                self.logger.info("映射為空，重建空索引")
                self._index = self._create_index()
                self._gpu_index = None
                return True
            
            # 對於非空映射，重建索引（這需要原始向量資料）
            self.logger.warning("無法直接修復過大索引，建議重新載入資料")
            return False
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "oversized index repair"))
            return False
    
    def _repair_oversized_mapping(self, target_size: int) -> bool:
        """修復映射過大的問題
        
        Args:
            target_size: 目標大小
            
        Returns:
            bool: 是否修復成功
        """
        try:
            if target_size == 0:
                # 清空所有映射
                self._id_map.clear()
                self._reverse_id_map.clear()
                self._next_id = 0
                self.logger.info("已清空所有映射")
                return True
            
            # 保留前 target_size 個映射
            sorted_faiss_ids = sorted(self._id_map.keys())
            valid_faiss_ids = sorted_faiss_ids[:target_size]
            
            # 重建映射
            new_id_map = {}
            new_reverse_map = {}
            
            for faiss_id in valid_faiss_ids:
                if faiss_id in self._id_map:
                    real_id = self._id_map[faiss_id]
                    new_id_map[faiss_id] = real_id
                    new_reverse_map[real_id] = faiss_id
            
            self._id_map = new_id_map
            self._reverse_id_map = new_reverse_map
            self._next_id = max(valid_faiss_ids) + 1 if valid_faiss_ids else 0
            
            self.logger.info(f"已修復映射，保留 {len(new_id_map)} 個有效映射")
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "oversized mapping repair"))
            return False
    
    def _repair_id_range_mismatch(self) -> bool:
        """修復 ID 範圍不匹配的問題
        
        Returns:
            bool: 是否修復成功
        """
        try:
            if not self._id_map:
                self._next_id = 0
                return True
            
            # 重新整理 ID 範圍
            max_id = max(self._id_map.keys())
            self._next_id = max_id + 1
            
            # 檢查並修復映射一致性
            fixed_mappings = 0
            for faiss_id, real_id in list(self._id_map.items()):
                if real_id not in self._reverse_id_map:
                    self._reverse_id_map[real_id] = faiss_id
                    fixed_mappings += 1
                elif self._reverse_id_map[real_id] != faiss_id:
                    # 移除不一致的映射
                    del self._id_map[faiss_id]
                    fixed_mappings += 1
            
            if fixed_mappings > 0:
                self.logger.info(f"修復了 {fixed_mappings} 個映射不一致問題")
            
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "ID range mismatch repair"))
            return False
    
    def _log_mapping_diagnostics(self, missing_mappings: List[int], index: faiss.Index) -> None:
        """記錄映射診斷資訊
        
        Args:
            missing_mappings: 缺失的映射 ID 列表
            index: 當前索引
        """
        try:
            # 統計資訊
            total_missing = len(missing_mappings)
            index_size = index.ntotal
            mapping_size = len(self._id_map)
            
            # 分析缺失模式
            missing_range = f"{min(missing_mappings)}-{max(missing_mappings)}" if missing_mappings else "無"
            
            diagnostic_info = {
                "缺失映射數量": total_missing,
                "索引總大小": index_size,
                "映射總數量": mapping_size,
                "缺失映射範圍": missing_range,
                "缺失比例": f"{(total_missing / index_size * 100):.1f}%" if index_size > 0 else "N/A",
                "映射完整性": f"{((mapping_size - total_missing) / index_size * 100):.1f}%" if index_size > 0 else "N/A"
            }
            
            self.logger.error(f"映射診斷報告: {diagnostic_info}")
            
            # 如果缺失比例過高，建議重建
            if index_size > 0 and (total_missing / index_size) > 0.1:
                self.logger.critical(
                    f"映射缺失比例過高({total_missing}/{index_size} = "
                    f"{(total_missing / index_size * 100):.1f}%)，強烈建議重建索引"
                )
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, "mapping diagnostics logging"))
    
    def _repair_oversized_mapping(self, target_size: int) -> bool:
        """修復映射過大的問題
        
        Args:
            target_size: 目標大小
            
        Returns:
            bool: 是否修復成功
        """
        try:
            if target_size == 0:
                # 清空所有映射
                self._id_map.clear()
                self._reverse_id_map.clear()
                self._next_id = 0
                self.logger.info("已清空所有映射")
                return True
            
            # 保留前 target_size 個映射
            sorted_faiss_ids = sorted(self._id_map.keys())
            valid_faiss_ids = sorted_faiss_ids[:target_size]
            
            # 重建映射
            new_id_map = {}
            new_reverse_map = {}
            
            for faiss_id in valid_faiss_ids:
                if faiss_id in self._id_map:
                    real_id = self._id_map[faiss_id]
                    new_id_map[faiss_id] = real_id
                    new_reverse_map[real_id] = faiss_id
            
            self._id_map = new_id_map
            self._reverse_id_map = new_reverse_map
            self._next_id = max(valid_faiss_ids) + 1 if valid_faiss_ids else 0
            
            self.logger.info(f"已修復映射，保留 {len(new_id_map)} 個有效映射")
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "oversized mapping repair"))
            return False
    
    def _repair_id_range_mismatch(self) -> bool:
        """修復 ID 範圍不匹配的問題
        
        Returns:
            bool: 是否修復成功
        """
        try:
            if not self._id_map:
                self._next_id = 0
                return True
            
            # 重新整理 ID 範圍
            max_id = max(self._id_map.keys())
            self._next_id = max_id + 1
            
            # 檢查並修復映射一致性
            fixed_mappings = 0
            for faiss_id, real_id in list(self._id_map.items()):
                if real_id not in self._reverse_id_map:
                    self._reverse_id_map[real_id] = faiss_id
                    fixed_mappings += 1
                elif self._reverse_id_map[real_id] != faiss_id:
                    # 移除不一致的映射
                    del self._id_map[faiss_id]
                    fixed_mappings += 1
            
            if fixed_mappings > 0:
                self.logger.info(f"修復了 {fixed_mappings} 個映射不一致問題")
            
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "ID range mismatch repair"))
            return False
    
    def _log_mapping_diagnostics(self, missing_mappings: List[int], index: faiss.Index) -> None:
        """記錄映射診斷資訊
        
        Args:
            missing_mappings: 缺失的映射 ID 列表
            index: 當前索引
        """
        try:
            # 統計資訊
            total_missing = len(missing_mappings)
            index_size = index.ntotal
            mapping_size = len(self._id_map)
            
            # 分析缺失模式
            missing_range = f"{min(missing_mappings)}-{max(missing_mappings)}" if missing_mappings else "無"
            
            diagnostic_info = {
                "缺失映射數量": total_missing,
                "索引總大小": index_size,
                "映射總數量": mapping_size,
                "缺失映射範圍": missing_range,
                "缺失比例": f"{(total_missing / index_size * 100):.1f}%" if index_size > 0 else "N/A",
                "映射完整性": f"{((mapping_size - total_missing) / index_size * 100):.1f}%" if index_size > 0 else "N/A"
            }
            
            self.logger.error(f"映射診斷報告: {diagnostic_info}")
            
            # 如果缺失比例過高，建議重建
            if index_size > 0 and (total_missing / index_size) > 0.1:
                self.logger.critical(
                    f"映射缺失比例過高({total_missing}/{index_size} = "
                    f"{(total_missing / index_size * 100):.1f}%)，強烈建議重建索引"
                )
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, "mapping diagnostics logging"))


class VectorManager:
    """向量管理器
    
    管理頻道級別的向量索引，提供索引建立、維護和搜尋功能。
    """
    
    def __init__(self, profile: MemoryProfile, storage_path: Optional[Path] = None):
        """初始化向量管理器
        
        Args:
            profile: 記憶系統配置檔案
            storage_path: 索引儲存路徑
        """
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"VectorManager __init__: 實例已創建，記憶體位址: {id(self)}")
        self.profile = profile
        self.storage_path = storage_path or Path("data/memory/indices")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._indices: Dict[str, VectorIndex] = {}
        self._indices_lock = threading.RLock()
        
        # 檢測 GPU 可用性
        self.use_gpu = (
            self.profile.vector_enabled and
            not getattr(profile, 'gpu_required', True) is False and
            faiss.get_num_gpus() > 0
        )
        
        # 初始化 GPU 記憶體管理器
        self.gpu_memory_manager: Optional[GPUMemoryManager] = None
        if self.use_gpu:
            try:
                # 根據配置檔案設定記憶體限制
                max_memory_mb = getattr(profile, 'gpu_memory_limit_mb', 1024)
                self.gpu_memory_manager = GPUMemoryManager(max_memory_mb)
                self.gpu_memory_manager.log_memory_stats()
            except Exception as e:
                asyncio.create_task(func.report_error(e, "GPU memory manager initialization"))
                self.gpu_memory_manager = None
        
        self.logger.info(
            f"向量管理器初始化 - GPU: {self.use_gpu}, "
            f"維度: {profile.embedding_dimension}, "
            f"記憶體管理: {'啟用' if self.gpu_memory_manager else '停用'}"
        )
        # 標記是否已關閉，避免重複清理
        self._shutdown = False
        
    def create_channel_index(self, channel_id: str) -> bool:
        """為頻道建立向量索引
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            bool: 是否成功
        """
        if not self.profile.vector_enabled:
            self.logger.debug(f"向量功能未啟用，跳過建立頻道 {channel_id} 的索引")
            return True
        
        try:
            with self._indices_lock:
                if channel_id not in self._indices:
                    # 決定索引類型
                    index_type = "Flat"  # 預設使用簡單索引
                    if self.profile.embedding_dimension > 0:
                        # 可以根據預期資料量選擇更適合的索引類型
                        # 目前使用 Flat 確保相容性
                        pass
                    
                    index = VectorIndex(
                        dimension=self.profile.embedding_dimension,
                        index_type=index_type,
                        metric="L2",
                        use_gpu=self.use_gpu,
                        gpu_memory_manager=self.gpu_memory_manager
                    )
                    
                    # 嘗試載入現有索引
                    index_file = self.storage_path / f"{channel_id}.index"
                    if index_file.exists():
                        # 先檢查索引維度相容性
                        try:
                            import faiss
                            temp_index = faiss.read_index(str(index_file))
                            if hasattr(temp_index, 'd') and temp_index.d != self.profile.embedding_dimension:
                                self.logger.warning(
                                    f"頻道 {channel_id} 索引維度不匹配 "
                                    f"(索引: {temp_index.d}, 期望: {self.profile.embedding_dimension})，重建索引"
                                )
                                # 備份舊索引
                                backup_file = index_file.with_suffix(f'.backup_dimension_mismatch_{int(time.time())}')
                                index_file.rename(backup_file)
                                self.logger.info(f"維度不匹配的舊索引已備份至: {backup_file}")
                                
                                # 同時備份映射檔案
                                mapping_file = index_file.with_suffix('.mapping')
                                if mapping_file.exists():
                                    backup_mapping = mapping_file.with_suffix(f'.backup_dimension_mismatch_{int(time.time())}')
                                    mapping_file.rename(backup_mapping)
                            else:
                                # 維度匹配，嘗試正常載入
                                if not index.load(index_file):
                                    self.logger.warning(f"載入頻道 {channel_id} 索引失敗，建立新索引")
                        except Exception as e:
                            self.logger.warning(f"檢查頻道 {channel_id} 索引時出錯: {e}，嘗試正常載入")
                            if index.load(index_file):
                                self.logger.info(f"已載入頻道 {channel_id} 的現有索引")
                            else:
                                self.logger.warning(f"載入頻道 {channel_id} 索引失敗，建立新索引")
                    else:
                        self.logger.debug(f"頻道 {channel_id} 沒有現有索引檔案，建立新索引")
                    
                    # 檢查是否需要重建映射（當使用了佔位符映射時）
                    if hasattr(index, '_needs_mapping_rebuild') and index._needs_mapping_rebuild:
                        self.logger.info(f"頻道 {channel_id} 需要重建映射，嘗試從資料庫恢復真實映射關係")
                        
                        # 嘗試從資料庫重建映射
                        if self._try_rebuild_mapping_from_database(channel_id, index):
                            self.logger.info(f"頻道 {channel_id} 映射重建成功")
                            index._needs_mapping_rebuild = False
                        else:
                            self.logger.warning(f"頻道 {channel_id} 映射重建失敗，將繼續使用佔位符映射")
                    
                    self._indices[channel_id] = index
                    
                    # 使用啟動日誌管理器記錄索引準備狀態
                    startup_logger = get_startup_logger()
                    if startup_logger and startup_logger.is_startup_mode:
                        is_new = not index_file.exists()
                        startup_logger.log_channel_index_ready(channel_id, is_new)
                    else:
                        self.logger.info(f"頻道 {channel_id} 的向量索引已準備就緒")
            
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"channel index creation for {channel_id}"))
            return False
    
    def get_channel_index(self, channel_id: str) -> Optional['VectorIndex']:
        """取得指定頻道的向量索引實例。"""
        with self._indices_lock:
            return self._indices.get(channel_id)

    def add_vectors(
        self,
        channel_id: str,
        vectors: np.ndarray,
        ids: List[str],
        batch_size: int = None
    ) -> bool:
        """新增向量到頻道索引
        
        Args:
            channel_id: 頻道 ID
            vectors: 向量陣列
            message_ids: 對應的訊息 ID 列表
            batch_size: 批次大小（可選）
            
        Returns:
            bool: 是否成功
        """
        if not self.profile.vector_enabled:
            return True
        
        try:
            # 確保索引存在
            if not self.create_channel_index(channel_id):
                return False
            
            with self._indices_lock:
                index = self._indices[channel_id]
                
                # 使用指定的批次大小或預設值
                if batch_size is None:
                    batch_size = getattr(self.profile, 'batch_size', 50)
                
                success = index.add_vectors(vectors, ids, batch_size)
                
                if success:
                    self.logger.debug(
                        f"已新增 {len(ids)} 個向量到頻道 {channel_id}"
                    )
                
                return success
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"vector addition to channel {channel_id}"))
            return False

    def remove_vectors(self, channel_id: str, ids: List[str]) -> int:
        """從頻道索引中移除向量。

        Args:
            channel_id: 頻道的 ID。
            ids: 要移除的向量的真實 ID 列表。

        Returns:
            int: 成功移除的向量數量。
        """
        if not ids:
            return 0
        
        try:
            with self._indices_lock:
                index = self._indices.get(channel_id)
                if index:
                    self.logger.info(f"在頻道 {channel_id} 中移除 {len(ids)} 個向量。")
                    removed_count = index.remove_vectors(ids)
                    if removed_count > 0:
                        self.logger.info(f"成功從頻道 {channel_id} 的索引中移除了 {removed_count} 個向量。")
                    return removed_count
                else:
                    self.logger.warning(f"嘗試從未載入的索引 {channel_id} 中移除向量。")
                    return 0
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"vector removal from channel {channel_id}"))
            raise VectorOperationError(f"從頻道 {channel_id} 移除向量失敗: {e}")
    
    def search_similar(
        self,
        channel_id: str,
        query_vector: np.ndarray,
        k: int = 10,
        score_threshold: float = None
    ) -> List[Tuple[str, float]]:
        """搜尋相似向量
        
        Args:
            channel_id: 頻道 ID
            query_vector: 查詢向量
            k: 返回結果數量
            score_threshold: 分數閾值
            
        Returns:
            List[Tuple[str, float]]: [(訊息ID, 相似度分數), ...]
        """
        if not self.profile.vector_enabled:
            return []
        
        try:
            with self._indices_lock:
                if channel_id not in self._indices:
                    self.logger.debug(f"頻道 {channel_id} 沒有向量索引，嘗試建立")
                    if not self.create_channel_index(channel_id):
                        self.logger.error(f"無法為頻道 {channel_id} 建立索引")
                        return []
                
                index = self._indices[channel_id]
                
                # 檢查索引狀態並嘗試修復
                index_stats = index.get_stats()
                total_vectors = index_stats.get("total_vectors", 0)
                
                if total_vectors == 0:
                    self.logger.warning(f"頻道 {channel_id} 的索引為空，嘗試重建")
                    if self._try_rebuild_index(channel_id):
                        # 重新獲取索引
                        index = self._indices[channel_id]
                        index_stats = index.get_stats()
                        total_vectors = index_stats.get("total_vectors", 0)
                    
                    if total_vectors == 0:
                        self.logger.warning(f"頻道 {channel_id} 重建後索引仍為空，嘗試從資料庫重新生成向量")
                        # 嘗試從資料庫重新生成向量資料
                        if self._try_regenerate_vectors(channel_id):
                            # 重新檢查索引
                            index = self._indices[channel_id]
                            index_stats = index.get_stats()
                            total_vectors = index_stats.get("total_vectors", 0)
                            if total_vectors > 0:
                                self.logger.info(f"頻道 {channel_id} 向量重新生成成功，現有 {total_vectors} 個向量")
                            else:
                                self.logger.warning(f"頻道 {channel_id} 向量重新生成後仍為空，可能該頻道無有效訊息資料")
                                return []
                        else:
                            self.logger.warning(f"頻道 {channel_id} 向量重新生成失敗")
                            return []
                
                distances, message_ids = index.search(query_vector, k)
                
                # 如果搜尋返回空結果但索引不為空，記錄警告
                if not distances and total_vectors > 0:
                    self.logger.warning(
                        f"頻道 {channel_id} 索引有 {total_vectors} 個向量但搜尋返回空結果"
                    )
                
                # 轉換距離為相似度分數（L2 距離轉換）
                results = []
                for distance, message_id in zip(distances, message_ids):
                    # L2 距離轉換為相似度分數 (0-1，越高越相似)
                    similarity = 1.0 / (1.0 + distance)
                    
                    if score_threshold is None or similarity >= score_threshold:
                        results.append((message_id, similarity))
                
                self.logger.debug(f"頻道 {channel_id} 搜尋完成，返回 {len(results)} 個結果")
                return results
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"similar vector search in channel {channel_id}"))
            # 嘗試索引修復
            try:
                self.logger.info(f"嘗試修復頻道 {channel_id} 的索引")
                if self._try_rebuild_index(channel_id):
                    self.logger.info(f"頻道 {channel_id} 索引修復成功，請重試搜尋")
                else:
                    self.logger.error(f"頻道 {channel_id} 索引修復失敗")
            except Exception as repair_error:
                asyncio.create_task(func.report_error(repair_error, f"index repair for channel {channel_id}"))
            
            return []
    
    def get_index_stats(self, channel_id: str) -> Dict[str, Union[int, str, bool]]:
        """取得頻道索引統計資訊
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            Dict[str, Union[int, str, bool]]: 統計資訊
        """
        try:
            with self._indices_lock:
                if channel_id in self._indices:
                    return self._indices[channel_id].get_stats()
                else:
                    return {"total_vectors": 0, "error": "索引不存在"}
                    
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"index stats retrieval for channel {channel_id}"))
            return {"error": str(e)}
    
    def unload_channel_index(self, channel_id: str) -> bool:
        """從記憶體中卸載特定頻道的索引。

        Args:
            channel_id: 要卸載索引的頻道 ID。

        Returns:
            bool: 如果成功卸載或索引本來就不存在，則返回 True。
        """
        try:
            with self._indices_lock:
                if channel_id in self._indices:
                    # 釋放與索引相關的資源
                    if hasattr(self._indices[channel_id], 'clear_gpu_resources'):
                        self._indices[channel_id].clear_gpu_resources()
                    
                    del self._indices[channel_id]
                    self.logger.info(f"成功從記憶體中卸載頻道 {channel_id} 的索引。")
                    # 觸發垃圾回收以釋放記憶體
                    gc.collect()
                    return True
                else:
                    self.logger.debug(f"頻道 {channel_id} 的索引未載入，無需卸載。")
                    return True
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"channel index unload for {channel_id}"))
            return False

    def _normalize_channel_id(self, channel_id: str) -> Optional[str]:
        """將各種可能格式的 channel_id 正規化為純數字字串。
        
        安全策略：
        - 若原本即為純數字，直接返回。
        - 若為 'segments_12345'、'channel_12345' 或其他包含數字的字串，提取最後一段連續數字作為 ID。
        - 若完全無法提取數字，回傳 None 以跳過儲存，避免寫出錯誤檔名。
        """
        try:
            if channel_id is None:
                return None
            s = str(channel_id)
            if s.isdigit():
                return s
            m = re.search(r'(\d+)$', s)
            if m:
                return m.group(1)
            return None
        except Exception as e:
            asyncio.create_task(func.report_error(e, "channel ID normalization"))
            return None

    async def save_index(self, channel_id: str) -> bool:
        """非同步儲存頻道索引

        Args:
            channel_id: 頻道 ID

        Returns:
            bool: 是否成功
        """
        try:
            with self._indices_lock:
                if channel_id in self._indices:
                    norm_cid = self._normalize_channel_id(channel_id)
                    if not norm_cid:
                        self.logger.critical(f"save_index: 無法正規化 channel_id='{channel_id}'，已跳過儲存以避免損壞檔名。")
                        return False
                    if norm_cid != channel_id:
                        self.logger.warning(f"save_index: 偵測到非純數字 channel_id='{channel_id}'，已正規化為 '{norm_cid}' 後儲存。")
                    index_file = self.storage_path / f"{norm_cid}.index"
                    return await self._indices[channel_id].save(index_file)
            return False
        except Exception as e:
            await func.report_error(e, f"index save for channel {channel_id}")
            return False
    
    async def save_all_indices(self) -> Dict[str, bool]:
        """並行儲存所有頻道索引
        
        Returns:
            Dict[str, bool]: 各頻道儲存結果
        """
        self.logger.info(f"開始並行儲存所有 {len(self._indices)} 個索引...")
        start_time = time.time()
        
        tasks = []
        with self._indices_lock:
            for channel_id in self._indices:
                tasks.append(self.save_index(channel_id))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        
        # 處理結果
        final_results = {}
        success_count = 0
        with self._indices_lock:
            channel_ids = list(self._indices.keys())
            for i, result in enumerate(results):
                channel_id = channel_ids[i]
                if isinstance(result, Exception):
                    self.logger.error(f"並行儲存頻道 {channel_id} 索引時發生錯誤: {result}")
                    final_results[channel_id] = False
                else:
                    final_results[channel_id] = result
                    if result:
                        success_count += 1

        self.logger.info(f"所有索引並行儲存完成，耗時: {end_time - start_time:.2f} 秒。{success_count}/{len(self._indices)} 個成功。")
        return final_results
    
    def optimize_index(self, channel_id: str) -> bool:
        """優化頻道索引
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            bool: 是否成功
        """
        # 目前使用簡單索引，暫不需要特殊優化
        # 未來可以實作索引重建、壓縮等功能
        self.logger.debug(f"頻道 {channel_id} 索引優化完成")
        return True
    
    async def clear_cache(self) -> None:
        """清除向量快取並釋放記憶體（非同步；將阻塞操作移至背景執行緒）"""
        # 快照索引並清空內部字典，避免在持有鎖時執行阻塞操作
        with self._indices_lock:
            indices_snapshot = list(self._indices.values())
            self._indices.clear()

        # 並行清除每個索引的 GPU 資源（在執行緒中執行）
        if indices_snapshot:
            await asyncio.gather(
                *(asyncio.to_thread(index.clear_gpu_resources) for index in indices_snapshot),
                return_exceptions=True
            )

        # 清理 GPU 記憶體管理器（在執行緒中執行）
        if self.gpu_memory_manager is not None:
            try:
                await asyncio.to_thread(self.gpu_memory_manager.clear_gpu_memory)
            except Exception as e:
                await func.report_error(e, "GPU memory manager cleanup")

        # 強制垃圾回收（在執行緒中執行，避免阻塞事件迴圈）
        try:
            await asyncio.to_thread(gc.collect)
        except Exception as e:
            self.logger.debug(f"gc.collect 失敗: {e}")

        self.logger.info("向量管理器快取已清除")
    
    def get_memory_stats(self) -> Dict[str, Union[int, float, str]]:
        """取得記憶體使用統計
        
        Returns:
            Dict[str, Union[int, float, str]]: 記憶體統計資訊
        """
        stats = {
            "total_indices": len(self._indices),
            "gpu_enabled": self.use_gpu,
            "gpu_memory_manager": self.gpu_memory_manager is not None
        }
        
        if self.gpu_memory_manager is not None:
            try:
                total_mb, free_mb, used_percent = self.gpu_memory_manager.get_gpu_memory_info()
                stats.update({
                    "gpu_total_memory_mb": total_mb,
                    "gpu_free_memory_mb": free_mb,
                    "gpu_used_percent": used_percent,
                    "gpu_memory_limit_mb": self.gpu_memory_manager.max_memory_mb
                })
            except Exception as e:
                asyncio.create_task(func.report_error(e, "GPU memory stats retrieval in get_memory_stats"))
                stats["gpu_memory_error"] = str(e)
        
        # 統計向量資料
        total_vectors = 0
        with self._indices_lock:
            for channel_id, index in self._indices.items():
                try:
                    index_stats = index.get_stats()
                    total_vectors += index_stats.get("total_vectors", 0)
                    stats[f"channel_{channel_id}_vectors"] = index_stats.get("total_vectors", 0)
                except Exception as e:
                    asyncio.create_task(func.report_error(e, f"index stats retrieval for channel {channel_id} in get_memory_stats"))
                    stats[f"channel_{channel_id}_error"] = str(e)
        
        stats["total_vectors"] = total_vectors
        
        return stats
    
    def rebuild_all_indexes(self) -> dict:
        """重建所有頻道/伺服器的向量索引（同步、供上層以執行緒池呼叫）
        
        掃描索引存放目錄的 *.index/.mapping，解析頻道 ID，從資料庫讀取原始訊息，
        重新分段、重新嵌入並建立乾淨索引後，以原子方式覆蓋舊檔。
        
        Returns:
            dict: {'rebuilt_count': int, 'failed_count': int, 'errors': List[str]}
        """
        summary = {'rebuilt_count': 0, 'failed_count': 0, 'errors': []}
        try:
            # 延伸：允許沒有現有檔案也重建（例如只有資料庫資料）
            existing_files = list(self.storage_path.glob("*.index"))
            channel_ids = set([p.stem for p in existing_files])
            
            # 若目錄存在但沒有檔案，仍嘗試從資料庫列出所有 channel
            try:
                from .database import DatabaseManager
                db_path = Path("data/memory/memory.db")
                db_manager = DatabaseManager(db_path) if db_path.exists() else None
            except Exception as e:
                asyncio.create_task(func.report_error(e, "DatabaseManager initialization failure"))
                db_manager = None
                self.logger.warning(f"初始化 DatabaseManager 失敗，僅重建現有索引檔案: {e}")
            
            # 當能訪問資料庫時，補齊所有 channels
            if db_manager:
                try:
                    # 讀出所有 channel_id
                    with db_manager.get_connection() as conn:
                        cursor = conn.execute("SELECT channel_id FROM channels")
                        for row in cursor.fetchall():
                            channel_ids.add(row[0])
                except Exception as e:
                    asyncio.create_task(func.report_error(e, "Database channel scanning failure"))
                    self.logger.warning(f"掃描資料庫頻道失敗，僅使用檔案清單: {e}")
            
            # 需要嵌入與分段服務，從上層 MemoryManager 初始化後掛載於此管理器
            embedding_service = getattr(self, "_embedding_service", None)
            segmentation_service = getattr(self, "_segmentation_service", None)
            
            if embedding_service is None or self.profile.embedding_dimension <= 0:
                raise VectorOperationError("嵌入服務未初始化或維度配置無效，無法重建索引")
            
            # 逐一重建
            for channel_id in sorted(channel_ids):
                try:
                    # 卸載記憶體中的舊索引，以避免佔用資源
                    self.unload_channel_index(channel_id)
                    
                    # 重新建立空索引容器
                    if not self.create_channel_index(channel_id):
                        raise VectorOperationError("建立空索引容器失敗")
                    
                    index = self.get_channel_index(channel_id)
                    if index is None:
                        raise VectorOperationError("取得索引實例失敗")
                    
                    # 從資料庫讀取該頻道所有訊息
                    messages = []
                    if db_manager:
                        try:
                            with db_manager.get_connection() as conn:
                                cursor = conn.execute(
                                    "SELECT message_id, content, timestamp, user_id FROM messages WHERE channel_id = ? ORDER BY timestamp ASC",
                                    (channel_id,)
                                )
                                messages = [dict(row) for row in cursor.fetchall()]
                        except Exception as e:
                            raise VectorOperationError(f"讀取資料庫訊息失敗: {e}")
                    
                    if not messages:
                        # 沒有資料，則建立空索引並覆蓋舊檔（若有）
                        index_file = self.storage_path / f"{channel_id}.index"
                        faiss.write_index(index.get_index(), str(index_file))
                        # 同步寫入空映射
                        mapping_path = index_file.with_suffix(".mapping")
                        with open(mapping_path, "wb") as f:
                            pickle.dump({'id_map': {}, 'reverse_id_map': {}, 'next_id': 0}, f)
                        summary['rebuilt_count'] += 1
                        self.logger.info(f"頻道 {channel_id}: 無訊息資料，已重置為空索引")
                        continue
                    
                    # 重新嵌入（簡化：直接使用訊息文本，若分段服務存在，可在此做分段）
                    texts = [m.get("content", "") for m in messages]
                    # 以批次方式產生嵌入以降低峰值記憶體
                    batch = getattr(self.profile, 'batch_size', 50) or 50
                    vectors: list = []
                    for i in range(0, len(texts), batch):
                        chunk = texts[i:i+batch]
                        embeds = embedding_service.encode(chunk)
                        # 支援 torch/np 兩種返回
                        if hasattr(embeds, 'cpu'):
                            embeds = embeds.cpu().numpy()
                        vectors.append(embeds.astype('float32'))
                    if vectors:
                        vectors_np = np.vstack(vectors)
                    else:
                        vectors_np = np.zeros((0, self.profile.embedding_dimension), dtype='float32')
                    
                    # 建立對應 ID（以 message_id 綁定）
                    ids = [str(m.get("message_id")) for m in messages]
                    
                    # 寫入全新索引（在記憶體，確保原子性保存時才覆蓋檔案）
                    if vectors_np.shape[0] != len(ids):
                        raise VectorOperationError("嵌入向量數與 ID 數量不一致")
                    
                    add_ok = index.add_vectors(vectors_np, ids, batch_size=batch)
                    if not add_ok:
                        raise VectorOperationError("新增向量至索引失敗")
                    
                    # 原子性覆寫檔案
                    index_file = self.storage_path / f"{channel_id}.index"
                    if not asyncio.get_event_loop().is_running():
                        # 在同步環境下直接存
                        faiss.write_index(index.get_index(), str(index_file))
                        # 同步寫映射
                        mapping_path = index_file.with_suffix(".mapping")
                        with open(mapping_path, "wb") as f:
                            pickle.dump({
                                'id_map': index._id_map,
                                'reverse_id_map': index._reverse_id_map,
                                'next_id': index._next_id,
                                'dimension': index.dimension,
                                'index_type': index.index_type,
                                'metric': index.metric,
                                'timestamp': time.time(),
                                'checksum': index._calculate_mapping_checksum(),
                            }, f)
                    else:
                        # 若在事件迴圈中，使用既有的異步存檔方法
                        save_ok = asyncio.get_event_loop().run_until_complete(index.save(index_file))  # type: ignore
                        if not save_ok:
                            raise VectorOperationError("索引保存失敗")
                    
                    summary['rebuilt_count'] += 1
                    self.logger.info(f"頻道 {channel_id}: 重建完成（{len(ids)} 筆）")
                
                except Exception as ce:
                    asyncio.create_task(func.report_error(ce, f"Channel {channel_id} rebuild failure"))
                    summary['failed_count'] += 1
                    err = f"頻道 {channel_id} 重建失敗: {ce}"
                    summary['errors'].append(err)
                    self.logger.error(err, exc_info=True)
            
            return summary
        
        except Exception as e:
            asyncio.create_task(func.report_error(e, "rebuild all indexes"))
            summary['failed_count'] += 1
            summary['errors'].append(str(e))
            return summary
    
    def optimize_memory_usage(self) -> bool:
        """優化記憶體使用
        
        Returns:
            bool: 是否成功優化
        """
        try:
            self.logger.info("開始記憶體優化...")
            
            # 檢查 GPU 記憶體狀態
            if self.gpu_memory_manager is not None:
                total_mb, free_mb, used_percent = self.gpu_memory_manager.get_gpu_memory_info()
                
                # 如果記憶體使用率過高，清理記憶體
                if used_percent > 80.0:
                    self.logger.warning(f"GPU 記憶體使用率過高 ({used_percent:.1f}%)，開始清理")
                    self.gpu_memory_manager.clear_gpu_memory()
                
                # 如果可用記憶體太少，強制降級某些索引到 CPU
                if free_mb < 256:
                    self.logger.warning(f"GPU 可用記憶體不足 ({free_mb}MB)，降級部分索引到 CPU")
                    self._fallback_indices_to_cpu()
            
            # 強制垃圾回收
            gc.collect()
            
            self.logger.info("記憶體優化完成")
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "memory usage optimization"))
            return False
    
    def _fallback_indices_to_cpu(self) -> None:
        """將部分索引降級到 CPU 以釋放 GPU 記憶體"""
        try:
            with self._indices_lock:
                # 按向量數量排序，優先降級較小的索引
                sorted_indices = sorted(
                    self._indices.items(),
                    key=lambda x: x[1].get_stats().get("total_vectors", 0)
                )
                
                fallback_count = 0
                for channel_id, index in sorted_indices:
                    if fallback_count >= 2:  # 最多降級 2 個索引
                        break
                    
                    if index._gpu_index is not None:
                        try:
                            index.clear_gpu_resources()
                            fallback_count += 1
                            self.logger.info(f"頻道 {channel_id} 索引已降級到 CPU")
                        except Exception as e:
                            self.logger.warning(f"降級頻道 {channel_id} 索引失敗: {e}")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "index fallback to CPU"))
    
    def _try_rebuild_index(self, channel_id: str) -> bool:
        """嘗試重建頻道索引
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            bool: 是否成功重建
        """
        try:
            self.logger.info(f"開始重建頻道 {channel_id} 的索引")
            
            # 檢查索引檔案
            index_file = self.storage_path / f"{channel_id}.index"
            rebuild_reason = None
            
            if index_file.exists():
                file_size = index_file.stat().st_size
                
                # 檢查檔案大小
                if file_size <= 45:
                    rebuild_reason = f"檔案大小異常 ({file_size} bytes)"
                else:
                    # 檢查維度相容性
                    try:
                        # 嘗試載入索引檢查維度
                        import faiss
                        temp_index = faiss.read_index(str(index_file))
                        if hasattr(temp_index, 'd') and temp_index.d != self.profile.embedding_dimension:
                            rebuild_reason = f"維度不匹配 (索引: {temp_index.d}, 期望: {self.profile.embedding_dimension})"
                    except Exception as e:
                        asyncio.create_task(func.report_error(e, "faiss.read_index failure"))
                        rebuild_reason = f"索引檔案損壞: {e}"
                
                if rebuild_reason:
                    self.logger.warning(f"檢測到問題索引 - {rebuild_reason}，開始重建")
                    try:
                        # 備份舊索引（以防需要恢復）
                        backup_file = index_file.with_suffix(f'.backup_{int(time.time())}')
                        index_file.rename(backup_file)
                        self.logger.info(f"舊索引已備份至: {backup_file}")
                        
                        # 同時處理映射檔案
                        mapping_file = index_file.with_suffix('.mapping')
                        if mapping_file.exists():
                            backup_mapping = mapping_file.with_suffix(f'.backup_{int(time.time())}')
                            mapping_file.rename(backup_mapping)
                            
                    except Exception as e:
                        asyncio.create_task(func.report_error(e, "backup failure"))
                        self.logger.warning(f"備份舊索引失敗: {e}")
                        # 即使備份失敗也繼續重建
                        try:
                            index_file.unlink()
                            mapping_file = index_file.with_suffix('.mapping')
                            if mapping_file.exists():
                                mapping_file.unlink()
                        except Exception as e2:
                            self.logger.warning(f"刪除舊索引失敗: {e2}")
            
            # 移除記憶體中的索引
            with self._indices_lock:
                if channel_id in self._indices:
                    try:
                        self._indices[channel_id].clear_gpu_resources()
                    except Exception as e:
                        asyncio.create_task(func.report_error(e, "GPU resource cleanup failure"))
                        self.logger.warning(f"清理 GPU 資源失敗: {e}")
                    del self._indices[channel_id]
            
            # 重新建立索引
            if self.create_channel_index(channel_id):
                if rebuild_reason:
                    self.logger.info(f"頻道 {channel_id} 索引重建成功 (原因: {rebuild_reason})")
                else:
                    self.logger.info(f"頻道 {channel_id} 索引重建成功")
                return True
            else:
                self.logger.error(f"頻道 {channel_id} 索引重建失敗")
                return False
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"index rebuild for channel {channel_id}"))
            return False
    
    def _try_regenerate_vectors(self, channel_id: str) -> bool:
        """嘗試從資料庫重新生成向量資料
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            bool: 是否成功重新生成
        """
        try:
            self.logger.info(f"開始為頻道 {channel_id} 重新生成向量資料")
            
            # 檢查是否有資料庫管理器可用
            # 這需要從外部傳入或透過某種方式獲取資料庫連接
            # 由於 VectorManager 通常不直接持有資料庫連接，
            # 我們先檢查是否有現有的訊息資料可以處理
            
            # 首先檢查資料庫檔案是否存在
            from pathlib import Path
            db_path = Path("data/memory/memory.db")
            if not db_path.exists():
                self.logger.warning(f"資料庫檔案不存在，無法重新生成頻道 {channel_id} 的向量")
                return False
            
            # 嘗試載入資料庫管理器
            try:
                from .database import DatabaseManager
                db_manager = DatabaseManager(str(db_path))
                
                # 檢查頻道是否存在訊息
                message_count = db_manager.get_message_count(channel_id)
                self.logger.info(f"頻道 {channel_id} 在資料庫中有 {message_count} 條訊息")
                
                if message_count == 0:
                    self.logger.info(f"頻道 {channel_id} 沒有訊息資料，無法生成向量")
                    return True  # 這不是錯誤，只是沒有資料
                
                # 獲取最近的一些訊息進行向量生成
                # 限制數量避免記憶體問題
                limit = min(message_count, 100)  # 先處理最近的 100 條訊息
                
                messages = db_manager.get_messages(
                    channel_id=channel_id,
                    limit=limit
                )
                
                if not messages:
                    self.logger.warning(f"無法從資料庫獲取頻道 {channel_id} 的訊息")
                    return False
                
                # 嘗試載入 embedding service
                from .embedding_service import embedding_service_manager
                embedding_service = embedding_service_manager.get_service(self.profile)
                
                if not embedding_service:
                    self.logger.error(f"無法初始化 embedding service，無法生成向量")
                    return False
                
                # 過濾有效訊息並生成向量
                valid_messages = []
                vectors_list = []
                
                for msg in messages:
                    content = msg.get('content', '').strip()
                    content_processed = msg.get('content_processed', '').strip()
                    
                    # 選擇最佳的內容進行向量化
                    text_to_embed = content_processed if content_processed and content_processed != 'None' else content
                    
                    if text_to_embed and len(text_to_embed) > 0:
                        try:
                            vector = embedding_service.encode_text(text_to_embed)
                            if vector is not None and vector.size > 0:
                                valid_messages.append(msg)
                                vectors_list.append(vector)
                        except Exception as e:
                            self.logger.warning(f"生成訊息 {msg.get('message_id')} 向量失敗: {e}")
                            continue
                
                if not valid_messages:
                    self.logger.warning(f"頻道 {channel_id} 沒有可生成向量的有效訊息")
                    return True  # 不是錯誤，只是沒有有效內容
                
                # 將向量添加到索引
                import numpy as np
                vectors_array = np.array(vectors_list).astype('float32')
                message_ids = [msg['message_id'] for msg in valid_messages]
                
                success = self.add_vectors(channel_id, vectors_array, message_ids)
                
                if success:
                    self.logger.info(f"成功為頻道 {channel_id} 重新生成 {len(message_ids)} 個向量")
                    return True
                else:
                    self.logger.error(f"為頻道 {channel_id} 添加重新生成的向量失敗")
                    return False
                
            except Exception as e:
                asyncio.create_task(func.report_error(e, "Database operation failure"))
                self.logger.error(f"重新生成頻道 {channel_id} 向量時資料庫操作失敗: {e}")
                return False
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"vector regeneration for channel {channel_id}"))
            return False
    
    def _try_rebuild_mapping_from_database(self, channel_id: str, index: 'VectorIndex') -> bool:
        """嘗試從資料庫重建索引的真實映射關係
        
        Args:
            channel_id: 頻道 ID
            index: 向量索引物件
            
        Returns:
            bool: 是否成功重建映射
        """
        try:
            self.logger.info(f"開始從資料庫重建頻道 {channel_id} 的映射關係")
            
            # 檢查資料庫檔案是否存在
            from pathlib import Path
            db_path = Path("data/memory/memory.db")
            if not db_path.exists():
                self.logger.warning(f"資料庫檔案不存在，無法重建頻道 {channel_id} 的映射")
                return False
            
            # 嘗試載入資料庫管理器
            try:
                from .database import DatabaseManager
                db_manager = DatabaseManager(str(db_path))
                
                # 獲取頻道中的所有訊息 ID（按時間排序）
                # 先獲取訊息總數
                message_count = db_manager.get_message_count(channel_id)
                
                # 使用足夠大的 limit 來獲取所有訊息（默認已按 timestamp DESC 排序）
                messages = db_manager.get_messages(
                    channel_id=channel_id,
                    limit=max(message_count, 10000)  # 使用較大的 limit 確保獲取所有訊息
                )
                
                # 由於資料庫返回的是按時間倒序，我們需要反轉以獲得正序
                messages = list(reversed(messages))
                
                if not messages:
                    self.logger.warning(f"頻道 {channel_id} 沒有訊息資料，無法重建映射")
                    return False
                
                # 檢查索引大小是否與訊息數量匹配
                index_size = index.get_index().ntotal
                message_count = len(messages)
                
                self.logger.info(f"頻道 {channel_id} - 索引大小: {index_size}, 資料庫訊息數: {message_count}")
                
                # 如果數量不匹配，我們只能嘗試重建部分映射
                messages_to_map = messages[:index_size] if message_count > index_size else messages
                
                # 重建映射
                new_id_map = {}
                new_reverse_map = {}
                
                for faiss_id, message in enumerate(messages_to_map):
                    message_id = message['message_id']
                    new_id_map[faiss_id] = message_id
                    new_reverse_map[message_id] = faiss_id
                
                # 檢查是否成功重建了大部分映射
                rebuilt_count = len(new_id_map)
                if rebuilt_count < index_size * 0.8:  # 至少重建 80% 的映射
                    self.logger.warning(
                        f"重建映射數量不足: {rebuilt_count}/{index_size} "
                        f"({rebuilt_count/index_size*100:.1f}%)，可能需要完整重建索引"
                    )
                    # 仍然使用重建的映射，但發出警告
                
                # 更新索引的映射
                index._id_map = new_id_map
                index._reverse_id_map = new_reverse_map
                index._next_id = len(new_id_map)
                
                self.logger.info(
                    f"成功重建頻道 {channel_id} 的映射: {rebuilt_count} 個映射關係 "
                    f"({rebuilt_count/index_size*100:.1f}% 完整性)"
                )
                
                # 儲存重建的映射
                index_file = self.storage_path / f"{channel_id}.index"
                if index_file.exists():
                    if index.save(index_file):
                        self.logger.info(f"已儲存重建的映射到: {index_file}")
                    else:
                        self.logger.warning(f"儲存重建的映射失敗: {index_file}")
                
                return True
                
            except Exception as e:
                asyncio.create_task(func.report_error(e, "Database operation failure"))
                self.logger.error(f"從資料庫重建頻道 {channel_id} 映射時資料庫操作失敗: {e}")
                return False
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"mapping rebuild from database for channel {channel_id}"))
            return False
    
    def clear_channel_mapping(self, channel_id: str) -> bool:
        """清除特定頻道的 ID 映射（用於強制重建）
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            bool: 是否成功
        """
        try:
            with self._indices_lock:
                if channel_id in self._indices:
                    index = self._indices[channel_id]
                    # 清除映射，強制重新建立
                    index._reverse_id_map.clear()
                    index._id_map.clear()
                    index._next_id = 0
                    self.logger.info(f"已清除頻道 {channel_id} 的 ID 映射")
                    return True
                else:
                    self.logger.warning(f"頻道 {channel_id} 的索引不存在")
                    return False
                    
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"channel mapping clear for {channel_id}"))
            return False
    
    def get_all_stats(self) -> Dict[str, Dict[str, Union[int, str, bool]]]:
        """取得所有頻道的索引統計
        
        Returns:
            Dict[str, Dict[str, Union[int, str, bool]]]: 所有頻道統計
        """
        stats = {}
        with self._indices_lock:
            for channel_id in self._indices:
                stats[channel_id] = self.get_index_stats(channel_id)
        return stats

    def get_all_segment_ids_by_channel(self) -> Dict[str, List[str]]:
        """
        獲取所有頻道及其對應的所有 segment ID。
        """
        all_ids = {}
        with self._indices_lock:
            for channel_id, index in self._indices.items():
                try:
                    # 確保索引已載入
                    if self.create_channel_index(channel_id):
                        all_ids[channel_id] = index.get_all_ids()
                except Exception as e:
                    asyncio.create_task(func.report_error(e, f"all segment ID retrieval for channel {channel_id}"))
        return all_ids
    
    def check_and_repair_all_indices(self) -> Dict[str, Dict[str, any]]:
        """檢查並修復所有頻道索引的完整性
        
        Returns:
            Dict[str, Dict[str, any]]: 各頻道的檢查和修復結果
        """
        results = {}
        
        try:
            self.logger.info("開始檢查所有頻道索引的完整性")
            
            with self._indices_lock:
                for channel_id, index in self._indices.items():
                    try:
                        self.logger.debug(f"檢查頻道 {channel_id} 的索引完整性")
                        
                        # 執行完整性檢查
                        integrity_issues = index._check_index_integrity()
                        
                        result = {
                            'channel_id': channel_id,
                            'has_issues': bool(integrity_issues),
                            'issues': integrity_issues,
                            'repair_attempted': False,
                            'repair_successful': False,
                            'index_stats': index.get_stats()
                        }
                        
                        if integrity_issues:
                            self.logger.warning(f"頻道 {channel_id} 檢測到完整性問題: {integrity_issues}")
                            
                            # 嘗試自動修復
                            result['repair_attempted'] = True
                            repair_success = index._attempt_auto_repair()
                            result['repair_successful'] = repair_success
                            
                            if repair_success:
                                self.logger.info(f"頻道 {channel_id} 完整性問題已修復")
                                
                                # 重新檢查修復效果
                                post_repair_issues = index._check_index_integrity()
                                result['post_repair_issues'] = post_repair_issues
                                
                                if not post_repair_issues:
                                    self.logger.info(f"頻道 {channel_id} 修復後完整性正常")
                                else:
                                    self.logger.warning(f"頻道 {channel_id} 修復後仍有問題: {post_repair_issues}")
                            else:
                                self.logger.error(f"頻道 {channel_id} 完整性問題修復失敗")
                        else:
                            self.logger.debug(f"頻道 {channel_id} 完整性檢查通過")
                        
                        results[channel_id] = result
                        
                    except Exception as e:
                        asyncio.create_task(func.report_error(e, f"Channel {channel_id} check failure"))
                        self.logger.error(f"檢查頻道 {channel_id} 時發生錯誤: {e}")
                        results[channel_id] = {
                            'channel_id': channel_id,
                            'error': str(e),
                            'has_issues': True,
                            'issues': [f"檢查過程中發生錯誤: {e}"],
                            'repair_attempted': False,
                            'repair_successful': False
                        }
            
            # 生成總結報告
            total_channels = len(results)
            channels_with_issues = sum(1 for r in results.values() if r.get('has_issues', False))
            repairs_attempted = sum(1 for r in results.values() if r.get('repair_attempted', False))
            repairs_successful = sum(1 for r in results.values() if r.get('repair_successful', False))
            
            self.logger.info(
                f"完整性檢查完成 - 總頻道: {total_channels}, "
                f"有問題: {channels_with_issues}, "
                f"嘗試修復: {repairs_attempted}, "
                f"修復成功: {repairs_successful}"
            )
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "check and repair all indices"))
            results['_error'] = str(e)
        
        return results
    
    def force_rebuild_problematic_indices(self, check_results: Dict[str, Dict[str, any]]) -> Dict[str, bool]:
        """強制重建有問題的索引
        
        Args:
            check_results: 完整性檢查結果
            
        Returns:
            Dict[str, bool]: 各頻道的重建結果
        """
        rebuild_results = {}
        
        try:
            # 找出需要重建的頻道
            channels_to_rebuild = [
                channel_id for channel_id, result in check_results.items()
                if (result.get('has_issues', False) and
                    not result.get('repair_successful', False) and
                    not channel_id.startswith('_'))
            ]
            
            if not channels_to_rebuild:
                self.logger.info("沒有需要強制重建的索引")
                return rebuild_results
            
            self.logger.info(f"開始強制重建 {len(channels_to_rebuild)} 個問題索引")
            
            for channel_id in channels_to_rebuild:
                try:
                    self.logger.info(f"開始重建頻道 {channel_id} 的索引")
                    
                    # 使用現有的重建方法
                    rebuild_success = self._try_rebuild_index(channel_id)
                    rebuild_results[channel_id] = rebuild_success
                    
                    if rebuild_success:
                        self.logger.info(f"頻道 {channel_id} 索引重建成功")
                    else:
                        self.logger.error(f"頻道 {channel_id} 索引重建失敗")
                        
                        # 嘗試從資料庫重新生成
                        self.logger.info(f"嘗試從資料庫重新生成頻道 {channel_id} 的向量")
                        regenerate_success = self._try_regenerate_vectors(channel_id)
                        
                        if regenerate_success:
                            self.logger.info(f"頻道 {channel_id} 向量重新生成成功")
                            rebuild_results[channel_id] = True
                        else:
                            self.logger.error(f"頻道 {channel_id} 向量重新生成也失敗")
                    
                except Exception as e:
                    asyncio.create_task(func.report_error(e, f"Channel {channel_id} rebuild failure"))
                    self.logger.error(f"重建頻道 {channel_id} 索引時發生錯誤: {e}")
                    rebuild_results[channel_id] = False
            
            # 統計重建結果
            successful_rebuilds = sum(rebuild_results.values())
            total_rebuilds = len(rebuild_results)
            
            self.logger.info(f"強制重建完成: {successful_rebuilds}/{total_rebuilds} 個成功")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "force rebuild problematic indices"))
            
        return rebuild_results
    
    def comprehensive_integrity_check_and_repair(self) -> Dict[str, any]:
        """執行綜合的完整性檢查和修復
        
        Returns:
            Dict[str, any]: 完整的檢查和修復報告
        """
        try:
            self.logger.info("開始綜合完整性檢查和修復")
            
            # 第一階段：檢查並修復現有索引
            check_results = self.check_and_repair_all_indices()
            
            # 第二階段：對無法修復的索引進行重建
            rebuild_results = self.force_rebuild_problematic_indices(check_results)
            
            # 第三階段：最終驗證
            final_check_results = {}
            if rebuild_results:
                self.logger.info("對重建的索引進行最終驗證")
                for channel_id in rebuild_results.keys():
                    if channel_id in self._indices:
                        try:
                            final_issues = self._indices[channel_id]._check_index_integrity()
                            final_check_results[channel_id] = {
                                'final_issues': final_issues,
                                'final_status': 'healthy' if not final_issues else 'problematic'
                            }
                        except Exception as e:
                            final_check_results[channel_id] = {
                                'final_error': str(e),
                                'final_status': 'error'
                            }
            
            # 生成綜合報告
            report = {
                'timestamp': time.time(),
                'initial_check': check_results,
                'rebuild_results': rebuild_results,
                'final_verification': final_check_results,
                'summary': {
                    'total_channels_checked': len([k for k in check_results.keys() if not k.startswith('_')]),
                    'channels_with_initial_issues': len([k for k, v in check_results.items()
                                                       if v.get('has_issues', False) and not k.startswith('_')]),
                    'channels_auto_repaired': len([k for k, v in check_results.items()
                                                 if v.get('repair_successful', False)]),
                    'channels_force_rebuilt': len([k for k, v in rebuild_results.items() if v]),
                    'final_healthy_channels': len([k for k, v in final_check_results.items()
                                                 if v.get('final_status') == 'healthy'])
                }
            }
            
            self.logger.info(f"綜合完整性檢查和修復完成: {report['summary']}")
            
            return report
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "comprehensive integrity check and repair"))
            return {
                'error': str(e),
                'timestamp': time.time(),
                'status': 'failed'
            }

    async def load_all_indexes(self) -> None:
        """
        載入所有存在於磁碟上的但尚未載入到記憶體中的索引。
        """
        self.logger.info("開始載入所有磁碟上的向量索引...")
        if not self.storage_path or not self.storage_path.exists():
            self.logger.warning("索引儲存路徑不存在，無法載入索引。")
            return

        loaded_count = 0
        failed_count = 0
        
        # 先收集所有需要載入的 channel_id
        channels_to_load = []
        try:
            index_files = list(self.storage_path.glob("*.index"))
            for index_file in index_files:
                channel_id = index_file.stem
                # 使用鎖來安全地檢查 self.indices
                with self._indices_lock:
                    if channel_id not in self._indices:
                        channels_to_load.append(channel_id)
        except Exception as e:
            await func.report_error(e, "index file scan")
            return
        
        if not channels_to_load:
            self.logger.info("沒有需要載入的新索引。")
            return

        self.logger.info(f"準備載入 {len(channels_to_load)} 個索引...")
        loop = asyncio.get_event_loop()

        for channel_id in channels_to_load:
            self.logger.debug(f"發現磁碟上的索引 {channel_id}，開始載入。")
            try:
                # create_channel_index 是 CPU 密集型操作，在執行緒池中運行
                success = await loop.run_in_executor(
                    None, self.create_channel_index, channel_id
                )
                if success:
                    loaded_count += 1
                else:
                    failed_count += 1
                    self.logger.error(f"載入索引 {channel_id} 失敗。")
            except Exception as e:
                await func.report_error(e, f"Index loading failure for channel {channel_id}")
                failed_count += 1
                self.logger.error(f"載入索引 {channel_id} 時發生例外: {e}")

        self.logger.info(f"所有索引載入完成。成功載入 {loaded_count} 個，失敗 {failed_count} 個。")

    def _cleanup_sync(self) -> None:
        """同步清理向量管理器（單執行緒、順序化，避免執行緒風暴）"""
        try:
            self.logger.info("開始向量管理器同步清理...")
            
            # 1) 儲存所有索引（在本執行緒中建立事件迴圈，順序執行）
            try:
                channel_ids = []
                with self._indices_lock:
                    channel_ids = list(self._indices.keys())
                if channel_ids:
                    loop = asyncio.new_event_loop()
                    try:
                        asyncio.set_event_loop(loop)
                        for channel_id in channel_ids:
                            try:
                                norm_cid = self._normalize_channel_id(channel_id)
                                if not norm_cid:
                                    self.logger.critical(f"_cleanup_sync: 無法正規化 channel_id='{channel_id}'，跳過此索引的儲存。")
                                    continue
                                if norm_cid != channel_id:
                                    self.logger.warning(f"_cleanup_sync: 偵測到非純數字 channel_id='{channel_id}'，改以 '{norm_cid}' 儲存索引檔。")
                                index_file = self.storage_path / f"{norm_cid}.index"
                                coro = self._indices[channel_id].save(index_file)
                                loop.run_until_complete(coro)
                            except Exception as e:
                                asyncio.create_task(func.report_error(e, f"Synchronous index saving failure for channel {channel_id}"))
                                self.logger.error(f"同步儲存頻道 {channel_id} 索引失敗: {e}")
                    finally:
                        try:
                            loop.run_until_complete(asyncio.sleep(0))
                        except Exception:
                            pass
                        loop.close()
                        asyncio.set_event_loop(None)
            except Exception as e:
                asyncio.create_task(func.report_error(e, "Overall synchronous index saving failure"))
                self.logger.error(f"同步儲存所有索引時發生錯誤: {e}")
            
            # 2) 釋放每個索引的 GPU 資源與快取（同步順序執行）
            indices_snapshot = []
            with self._indices_lock:
                indices_snapshot = list(self._indices.values())
                self._indices.clear()
            for index in indices_snapshot:
                try:
                    index.clear_gpu_resources()
                except Exception as e:
                    asyncio.create_task(func.report_error(e, "Index GPU resource cleanup failure"))
                    self.logger.warning(f"清理索引 GPU 資源失敗: {e}")
            
            # 3) 記憶體最佳化（同步）
            try:
                self.optimize_memory_usage()
            except Exception as e:
                asyncio.create_task(func.report_error(e, "Memory optimization failure"))
                self.logger.warning(f"記憶體最佳化失敗: {e}")
            
            # 4) 清理 GPU 記憶體管理器（同步）
            if self.gpu_memory_manager is not None:
                try:
                    self.gpu_memory_manager.clear_gpu_memory()
                except Exception as e:
                    asyncio.create_task(func.report_error(e, "GPU memory manager cleanup failure"))
                    self.logger.warning(f"清理 GPU 記憶體管理器失敗: {e}")
                finally:
                    self.gpu_memory_manager = None
            
            # 5) 垃圾回收
            try:
                gc.collect()
            except Exception:
                pass
            
            self.logger.debug("向量管理器同步清理完成")
        except Exception as e:
            asyncio.create_task(func.report_error(e, "vector manager sync cleanup"))
    
    async def cleanup(self) -> None:
        """非同步介面：統一委派至單一 to_thread 的同步清理"""
        try:
            await asyncio.to_thread(self._cleanup_sync)
        except Exception as e:
            await func.report_error(e, "vector manager cleanup")

    async def shutdown(self) -> None:
        """優雅關閉 VectorManager，確保同步清理只執行一次。"""
        if getattr(self, "_shutdown", False):
            return
        try:
            await self.cleanup()
        finally:
            # 標記已關閉，避免重入
            self._shutdown = True

    def move_all_indices_to_cpu(self):
        """將所有 GPU 索引批量移至 CPU"""
        self.logger.info("開始將所有 GPU 索引批量移至 CPU...")
        start_time = time.time()
        
        indices_to_move = []
        with self._indices_lock:
            for channel_id, index in self._indices.items():
                if index._gpu_index is not None:
                    indices_to_move.append((channel_id, index))

        if not indices_to_move:
            self.logger.info("沒有需要移動的 GPU 索引。")
            return

        for channel_id, index in indices_to_move:
            try:
                cpu_index = faiss.index_gpu_to_cpu(index._gpu_index)
                index._index = cpu_index
                index._gpu_index = None # 清除 GPU 索引參考
                self.logger.debug(f"頻道 {channel_id} 的索引已移至 CPU。")
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"index move to CPU for channel {channel_id}"))
        
        # 進行一次手動的垃圾回收
        gc.collect()
        if TORCH_AVAILABLE and torch.cuda.is_available():
            torch.cuda.synchronize() # 等待所有 CUDA 操作完成
            torch.cuda.empty_cache()

        end_time = time.time()
        self.logger.info(f"所有 {len(indices_to_move)} 個 GPU 索引已移至 CPU，總耗時: {end_time - start_time:.2f} 秒")

# --- 單例模式實作 ---
_vector_manager_instance: Optional[VectorManager] = None
_vector_manager_lock = threading.Lock()

def get_vector_manager(
    profile: Optional[MemoryProfile] = None,
    storage_path: Optional[Path] = None
) -> VectorManager:
    """
    獲取 VectorManager 的單例實例。

    Args:
        profile: 記憶系統配置檔案 (僅在首次初始化時需要)。
        storage_path: 索引儲存路徑 (僅在首次初始化時需要)。

    Returns:
        VectorManager: VectorManager 的單例實例。
        
    Raises:
        ValueError: 如果在未初始化時未提供 profile 或 storage_path。
    """
    global _vector_manager_instance
    try:
        if _vector_manager_instance is None:
            with _vector_manager_lock:
                if _vector_manager_instance is None:
                    if profile is None or storage_path is None:
                        raise ValueError("首次初始化 VectorManager 時必須提供 profile 和 storage_path。")
                    _vector_manager_instance = VectorManager(profile, storage_path)
        return _vector_manager_instance
    except Exception as e:
        asyncio.create_task(func.report_error(e, "vector manager singleton retrieval"))
        raise

# 在解譯器退出時作為最後保障，嘗試同步清理 VectorManager 的資源，避免背景執行緒阻塞退出
import atexit as _vx_atexit

def _vector_manager_atexit_cleanup():
    try:
        # 僅在單例已建立時清理；避免在未初始化時誤觸
        if _vector_manager_instance is not None:
            try:
                _vector_manager_instance._cleanup_sync()
            except Exception as e:
                # 退出流程中不可再拋出例外
                # but we can still try to report it
                try:
                    asyncio.create_task(func.report_error(e, "_vector_manager_atexit_cleanup failure"))
                except:
                    pass
    except Exception as e:
        try:
            asyncio.create_task(func.report_error(e, "_vector_manager_atexit_cleanup failure"))
        except:
            pass

_vx_atexit.register(_vector_manager_atexit_cleanup)