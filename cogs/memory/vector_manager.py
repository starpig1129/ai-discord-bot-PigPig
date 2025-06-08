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
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import faiss
import numpy as np

from .config import MemoryProfile
from .exceptions import VectorOperationError
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
    pynvml.nvmlInit()
except ImportError:
    PYNVML_AVAILABLE = False


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
        
    def get_gpu_memory_info(self) -> Tuple[int, int, float]:
        """取得 GPU 記憶體資訊
        
        Returns:
            Tuple[int, int, float]: (總記憶體MB, 可用記憶體MB, 使用率%)
        """
        try:
            if PYNVML_AVAILABLE:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                total_mb = memory_info.total // (1024 * 1024)
                free_mb = memory_info.free // (1024 * 1024)
                used_percent = ((memory_info.total - memory_info.free) / memory_info.total) * 100
                return total_mb, free_mb, used_percent
            elif TORCH_AVAILABLE and torch.cuda.is_available():
                total_mb = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
                allocated_mb = torch.cuda.memory_allocated(0) // (1024 * 1024)
                free_mb = total_mb - allocated_mb
                used_percent = (allocated_mb / total_mb) * 100
                return total_mb, free_mb, used_percent
        except Exception as e:
            self.logger.warning(f"無法取得 GPU 記憶體資訊: {e}")
        
        return 0, 0, 0.0
    
    def is_memory_available(self, required_mb: int = 512) -> bool:
        """檢查是否有足夠的 GPU 記憶體
        
        Args:
            required_mb: 需要的記憶體量（MB）
            
        Returns:
            bool: 是否有足夠記憶體
        """
        try:
            _, free_mb, used_percent = self.get_gpu_memory_info()
            
            # 檢查可用記憶體和使用率
            if free_mb < required_mb:
                self.logger.warning(f"GPU 記憶體不足: 需要 {required_mb}MB，可用 {free_mb}MB")
                return False
            
            if used_percent > 85.0:  # 使用率超過 85% 時警告
                self.logger.warning(f"GPU 記憶體使用率過高: {used_percent:.1f}%")
                return False
                
            return True
        except Exception as e:
            self.logger.error(f"檢查 GPU 記憶體失敗: {e}")
            return False
    
    def get_gpu_resource(self) -> Optional[faiss.StandardGpuResources]:
        """取得 GPU 資源實例（單例模式）
        
        Returns:
            Optional[faiss.StandardGpuResources]: GPU 資源實例
        """
        with self._memory_lock:
            if self._gpu_resource is None:
                try:
                    # 檢查記憶體是否可用
                    if not self.is_memory_available(self.max_memory_mb):
                        self.logger.warning("GPU 記憶體不足，無法建立 GPU 資源")
                        return None
                    
                    self.logger.info(f"開始建立 GPU 資源，記憶體限制: {self.max_memory_mb}MB")
                    
                    # 添加超時保護的 GPU 資源建立
                    import signal
                    import threading
                    
                    def timeout_handler(signum, frame):
                        raise TimeoutError("GPU 資源建立超時")
                    
                    def create_gpu_resource():
                        return faiss.StandardGpuResources()
                    
                    # 使用執行緒方式避免信號干擾
                    result = [None]
                    exception = [None]
                    
                    def worker():
                        try:
                            result[0] = create_gpu_resource()
                        except Exception as e:
                            exception[0] = e
                    
                    thread = threading.Thread(target=worker)
                    thread.daemon = True
                    thread.start()
                    thread.join(timeout=30.0)  # 30秒超時
                    
                    if thread.is_alive():
                        self.logger.error("GPU 資源建立超時（30秒），放棄建立")
                        return None
                    
                    if exception[0]:
                        raise exception[0]
                    
                    if result[0] is None:
                        self.logger.error("GPU 資源建立失敗，結果為空")
                        return None
                    
                    self._gpu_resource = result[0]
                    
                    # 設定記憶體限制
                    temp_memory_mb = min(self.max_memory_mb // 4, 512)  # 更保守的暫存記憶體
                    self._gpu_resource.setTempMemory(temp_memory_mb * 1024 * 1024)
                    
                    self.logger.info(f"GPU 資源建立成功，記憶體限制: {self.max_memory_mb}MB，暫存: {temp_memory_mb}MB")
                    
                except Exception as e:
                    self.logger.error(f"建立 GPU 資源失敗: {e}")
                    self._gpu_resource = None
            
            return self._gpu_resource
    
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
            
        except Exception as e:
            self.logger.error(f"清除 GPU 記憶體失敗: {e}")
    
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
            self.logger.error(f"記錄記憶體統計失敗: {e}")


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
        gpu_memory_manager: Optional[GPUMemoryManager] = None
    ):
        """初始化向量索引
        
        Args:
            dimension: 向量維度
            index_type: 索引類型 ("Flat", "IVFFlat", "HNSW" 等)
            metric: 距離度量 ("L2", "IP")
            use_gpu: 是否使用 GPU
            gpu_memory_manager: GPU 記憶體管理器
        """
        self.dimension = dimension
        self.index_type = index_type
        self.metric = metric
        self.use_gpu = use_gpu
        self.gpu_memory_manager = gpu_memory_manager
        self._index: Optional[faiss.Index] = None
        self._gpu_index: Optional[faiss.Index] = None
        self._id_map: Dict[int, str] = {}  # FAISS ID -> 實際 ID 映射
        self._reverse_id_map: Dict[str, int] = {}  # 實際 ID -> FAISS ID 映射
        self._next_id = 0
        self._gpu_fallback_warned = False  # GPU 降級警告標記
        self.logger = logging.getLogger(__name__)
    
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
                index = faiss.IndexHNSWFlat(self.dimension, 32)
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
        """嘗試將索引移至 GPU
        
        Returns:
            bool: 是否成功移至 GPU
        """
        try:
            # 檢查 GPU 記憶體管理器
            if self.gpu_memory_manager is None:
                if not self._gpu_fallback_warned:
                    self.logger.warning("沒有 GPU 記憶體管理器，使用預設 GPU 資源")
                    self._gpu_fallback_warned = True
                
                # 使用預設 GPU 資源（有風險）
                gpu_resource = faiss.StandardGpuResources()
            else:
                # 使用管理的 GPU 資源
                gpu_resource = self.gpu_memory_manager.get_gpu_resource()
                if gpu_resource is None:
                    if not self._gpu_fallback_warned:
                        self.logger.warning("GPU 記憶體不足，降級使用 CPU")
                        self._gpu_fallback_warned = True
                    return False
            
            # 估算索引記憶體需求
            estimated_memory_mb = self._estimate_index_memory()
            
            # 檢查記憶體是否足夠
            if (self.gpu_memory_manager is not None and
                not self.gpu_memory_manager.is_memory_available(estimated_memory_mb)):
                if not self._gpu_fallback_warned:
                    self.logger.warning(
                        f"GPU 記憶體不足（需要 {estimated_memory_mb}MB），使用 CPU"
                    )
                    self._gpu_fallback_warned = True
                return False
            
            # 移至 GPU
            self._gpu_index = faiss.index_cpu_to_gpu(gpu_resource, 0, self._index)
            
            # 使用啟動日誌管理器記錄 GPU 遷移
            startup_logger = get_startup_logger()
            if startup_logger and startup_logger.is_startup_mode:
                startup_logger.log_gpu_index_migration("unknown", estimated_memory_mb)
            else:
                self.logger.info(f"索引已移至 GPU（預估記憶體: {estimated_memory_mb}MB）")
            
            # 記錄記憶體狀態
            if self.gpu_memory_manager is not None:
                self.gpu_memory_manager.log_memory_stats()
            
            return True
            
        except Exception as e:
            if not self._gpu_fallback_warned:
                self.logger.warning(f"無法將索引移至 GPU，降級使用 CPU: {e}")
                self._gpu_fallback_warned = True
            
            # 清除可能部分建立的 GPU 索引
            self._gpu_index = None
            
            # 清理 GPU 記憶體
            if self.gpu_memory_manager is not None:
                self.gpu_memory_manager.clear_gpu_memory()
            
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
            self.logger.warning(f"估算索引記憶體失敗: {e}")
            return 512  # 預設值
    
    def add_vectors(self, vectors: np.ndarray, ids: List[str], batch_size: int = 50) -> bool:
        """新增向量到索引（支援批次處理）
        
        Args:
            vectors: 向量陣列，形狀為 (n, dimension)
            ids: 對應的 ID 列表
            batch_size: 批次大小
            
        Returns:
            bool: 是否成功
        """
        try:
            if len(vectors) != len(ids):
                raise ValueError("向量數量與 ID 數量不符")
            
            # 轉換為 float32
            vectors = vectors.astype('float32')
            
            # 建立 ID 映射
            new_vectors = []
            new_ids = []
            
            for i, id_str in enumerate(ids):
                if id_str not in self._reverse_id_map:
                    faiss_id = self._next_id
                    self._id_map[faiss_id] = id_str
                    self._reverse_id_map[id_str] = faiss_id
                    self._next_id += 1
                    new_vectors.append(vectors[i])
                    new_ids.append(faiss_id)
                else:
                    # 已存在的向量，跳過
                    self.logger.debug(f"向量 ID {id_str} 已存在，跳過")
                    continue
            
            if not new_vectors:
                return True
            
            new_vectors = np.array(new_vectors)
            
            # 批次處理新增向量
            return self._add_vectors_batch(new_vectors, new_ids, batch_size)
            
        except Exception as e:
            self.logger.error(f"新增向量失敗: {e}")
            return False
    
    def _add_vectors_batch(self, vectors: np.ndarray, faiss_ids: List[int], batch_size: int) -> bool:
        """批次新增向量到索引
        
        Args:
            vectors: 向量陣列
            faiss_ids: FAISS ID 列表
            batch_size: 批次大小
            
        Returns:
            bool: 是否成功
        """
        try:
            index = self.get_index()
            total_vectors = len(vectors)
            
            for i in range(0, total_vectors, batch_size):
                end_idx = min(i + batch_size, total_vectors)
                batch_vectors = vectors[i:end_idx]
                
                # 檢查 GPU 記憶體（如果使用 GPU）
                if (self._gpu_index is not None and
                    self.gpu_memory_manager is not None):
                    
                    # 估算批次記憶體需求
                    batch_memory_mb = (len(batch_vectors) * self.dimension * 4) // (1024 * 1024)
                    
                    if not self.gpu_memory_manager.is_memory_available(batch_memory_mb + 128):
                        self.logger.warning(
                            f"GPU 記憶體不足，批次 {i//batch_size + 1} 降級使用 CPU"
                        )
                        # 暫時降級到 CPU
                        if self._index is not None:
                            self._index.add(batch_vectors)
                        else:
                            self.logger.error("CPU 索引不可用")
                            return False
                    else:
                        index.add(batch_vectors)
                else:
                    index.add(batch_vectors)
                
                self.logger.debug(f"批次 {i//batch_size + 1}/{(total_vectors + batch_size - 1)//batch_size} 完成")
                
                # 定期清理記憶體
                if (i + batch_size) % (batch_size * 4) == 0:  # 每 4 個批次清理一次
                    gc.collect()
            
            self.logger.debug(f"成功新增 {total_vectors} 個向量到索引")
            return True
            
        except Exception as e:
            self.logger.error(f"批次新增向量失敗: {e}")
            return False
    
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
            
            self.logger.debug(
                f"開始向量搜尋: 查詢維度={query_vector.shape}, "
                f"索引向量數={index.ntotal}, k={search_k}"
            )
            
            # 執行搜尋
            distances, indices = index.search(query_vector, search_k)
            
            # 轉換結果
            result_distances = []
            result_ids = []
            
            for dist, idx in zip(distances[0], indices[0]):
                if idx != -1 and idx in self._id_map:  # -1 表示無效結果
                    result_distances.append(float(dist))
                    result_ids.append(self._id_map[idx])
                elif idx != -1:
                    self.logger.warning(f"找到向量索引 {idx} 但無對應的 ID 映射")
            
            self.logger.debug(f"向量搜尋完成，返回 {len(result_ids)} 個結果")
            return result_distances, result_ids
            
        except Exception as e:
            # 提供詳細的錯誤資訊
            error_details = {
                "error": str(e),
                "query_vector_shape": getattr(query_vector, 'shape', 'unknown'),
                "index_ntotal": getattr(index, 'ntotal', 'unknown') if 'index' in locals() else 'not_created',
                "index_dimension": getattr(index, 'd', 'unknown') if 'index' in locals() else 'not_created',
                "expected_dimension": self.dimension,
                "id_map_size": len(self._id_map)
            }
            self.logger.error(f"向量搜尋失敗: {error_details}")
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
    
    def save(self, file_path: Path) -> bool:
        """儲存索引到檔案
        
        Args:
            file_path: 儲存路徑
            
        Returns:
            bool: 是否成功
        """
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 決定要儲存的索引
            index_to_save = None
            
            # 如果有 GPU 索引，需要先複製回 CPU
            if self._gpu_index is not None:
                try:
                    # 將 GPU 索引複製回 CPU 進行儲存
                    index_to_save = faiss.index_gpu_to_cpu(self._gpu_index)
                    self.logger.debug("GPU 索引已複製到 CPU 進行儲存")
                except Exception as e:
                    self.logger.warning(f"GPU 索引複製失敗，使用 CPU 索引: {e}")
                    index_to_save = self._index
            else:
                # 使用 CPU 索引
                index_to_save = self._index
            
            if index_to_save is not None:
                # 儲存 FAISS 索引
                faiss.write_index(index_to_save, str(file_path))
                
                # 儲存 ID 映射
                mapping_path = file_path.with_suffix('.mapping')
                with open(mapping_path, 'wb') as f:
                    pickle.dump({
                        'id_map': self._id_map,
                        'reverse_id_map': self._reverse_id_map,
                        'next_id': self._next_id,
                        'dimension': self.dimension,
                        'index_type': self.index_type,
                        'metric': self.metric
                    }, f)
                
                # 驗證儲存的檔案大小
                file_size = file_path.stat().st_size
                vector_count = index_to_save.ntotal
                self.logger.info(
                    f"索引已儲存到: {file_path} "
                    f"(檔案大小: {file_size} bytes, 向量數量: {vector_count})"
                )
                
                # 檢查是否為空索引
                if file_size <= 45 and vector_count > 0:
                    self.logger.error(
                        f"警告：索引檔案大小異常小 ({file_size} bytes)，"
                        f"但索引包含 {vector_count} 個向量"
                    )
                
                return True
            
            self.logger.error("沒有可用的索引進行儲存")
            return False
            
        except Exception as e:
            self.logger.error(f"儲存索引失敗: {e}")
            return False
    
    def load(self, file_path: Path) -> bool:
        """從檔案載入索引
        
        Args:
            file_path: 索引檔案路徑
            
        Returns:
            bool: 是否成功
        """
        try:
            if not file_path.exists():
                return False
            
            # 載入 FAISS 索引
            self._index = faiss.read_index(str(file_path))
            
            # 載入 ID 映射
            mapping_path = file_path.with_suffix('.mapping')
            if mapping_path.exists():
                with open(mapping_path, 'rb') as f:
                    data = pickle.load(f)
                    self._id_map = data['id_map']
                    self._reverse_id_map = data['reverse_id_map']
                    self._next_id = data['next_id']
            
            # 嘗試移至 GPU（使用優化的記憶體管理）
            if self.use_gpu and faiss.get_num_gpus() > 0:
                self._try_move_to_gpu()
            
            return True
            
        except Exception as e:
            self.logger.error(f"載入索引失敗: {e}")
            return False
    
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
            self.logger.error(f"清除 GPU 資源失敗: {e}")


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
                self.logger.warning(f"GPU 記憶體管理器初始化失敗: {e}")
                self.gpu_memory_manager = None
        
        self.logger.info(
            f"向量管理器初始化 - GPU: {self.use_gpu}, "
            f"維度: {profile.embedding_dimension}, "
            f"記憶體管理: {'啟用' if self.gpu_memory_manager else '停用'}"
        )
    
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
            self.logger.error(f"建立頻道 {channel_id} 索引失敗: {e}")
            return False
    
    def add_vectors(
        self,
        channel_id: str,
        vectors: np.ndarray,
        message_ids: List[str],
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
                
                success = index.add_vectors(vectors, message_ids, batch_size)
                
                if success:
                    self.logger.debug(
                        f"已新增 {len(message_ids)} 個向量到頻道 {channel_id}"
                    )
                
                return success
                
        except Exception as e:
            self.logger.error(f"新增向量到頻道 {channel_id} 失敗: {e}")
            return False
    
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
            self.logger.error(f"搜尋頻道 {channel_id} 向量失敗: {e}")
            # 嘗試索引修復
            try:
                self.logger.info(f"嘗試修復頻道 {channel_id} 的索引")
                if self._try_rebuild_index(channel_id):
                    self.logger.info(f"頻道 {channel_id} 索引修復成功，請重試搜尋")
                else:
                    self.logger.error(f"頻道 {channel_id} 索引修復失敗")
            except Exception as repair_error:
                self.logger.error(f"索引修復過程出錯: {repair_error}")
            
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
            self.logger.error(f"取得頻道 {channel_id} 索引統計失敗: {e}")
            return {"error": str(e)}
    
    def save_index(self, channel_id: str) -> bool:
        """儲存頻道索引
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            bool: 是否成功
        """
        try:
            with self._indices_lock:
                if channel_id in self._indices:
                    index_file = self.storage_path / f"{channel_id}.index"
                    return self._indices[channel_id].save(index_file)
                return False
                
        except Exception as e:
            self.logger.error(f"儲存頻道 {channel_id} 索引失敗: {e}")
            return False
    
    def save_all_indices(self) -> Dict[str, bool]:
        """儲存所有頻道索引
        
        Returns:
            Dict[str, bool]: 各頻道儲存結果
        """
        results = {}
        with self._indices_lock:
            for channel_id in self._indices:
                results[channel_id] = self.save_index(channel_id)
        
        success_count = sum(results.values())
        self.logger.info(f"索引儲存完成: {success_count}/{len(results)} 個成功")
        return results
    
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
    
    def clear_cache(self) -> None:
        """清除向量快取並釋放記憶體"""
        with self._indices_lock:
            # 清除每個索引的 GPU 資源
            for index in self._indices.values():
                try:
                    index.clear_gpu_resources()
                except Exception as e:
                    self.logger.warning(f"清除索引 GPU 資源失敗: {e}")
            
            self._indices.clear()
        
        # 清理 GPU 記憶體管理器
        if self.gpu_memory_manager is not None:
            self.gpu_memory_manager.clear_gpu_memory()
            
        # 強制垃圾回收
        gc.collect()
        
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
                    stats[f"channel_{channel_id}_error"] = str(e)
        
        stats["total_vectors"] = total_vectors
        
        return stats
    
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
            self.logger.error(f"記憶體優化失敗: {e}")
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
            self.logger.error(f"索引降級失敗: {e}")
    
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
            self.logger.error(f"重建頻道 {channel_id} 索引時發生錯誤: {e}")
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
                self.logger.error(f"重新生成頻道 {channel_id} 向量時資料庫操作失敗: {e}")
                return False
                
        except Exception as e:
            self.logger.error(f"重新生成頻道 {channel_id} 向量失敗: {e}")
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
            self.logger.error(f"清除頻道 {channel_id} 映射失敗: {e}")
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
    
    def cleanup(self) -> None:
        """清理向量管理器資源和快取
        
        執行完整的清理作業，儲存所有索引並釋放記憶體資源。
        """
        try:
            self.logger.info("開始向量管理器清理...")
            
            # 首先儲存所有索引
            try:
                save_results = self.save_all_indices()
                success_count = sum(save_results.values())
                self.logger.info(f"向量索引儲存: {success_count}/{len(save_results)} 個成功")
            except Exception as e:
                self.logger.error(f"儲存索引時發生錯誤: {e}")
            
            # 清理所有快取和 GPU 資源
            self.clear_cache()
            
            # 額外的記憶體優化
            try:
                self.optimize_memory_usage()
            except Exception as e:
                self.logger.warning(f"記憶體優化失敗: {e}")
            
            # 清理 GPU 記憶體管理器
            if self.gpu_memory_manager is not None:
                try:
                    self.gpu_memory_manager.clear_gpu_memory()
                    self.gpu_memory_manager = None
                except Exception as e:
                    self.logger.warning(f"清理 GPU 記憶體管理器失敗: {e}")
            
            self.logger.info("向量管理器清理完成")
            
        except Exception as e:
            self.logger.error(f"向量管理器清理時發生錯誤: {e}")