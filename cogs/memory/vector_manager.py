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
                    
                    self._gpu_resource = faiss.StandardGpuResources()
                    
                    # 設定記憶體限制
                    temp_memory_mb = min(self.max_memory_mb, 512)  # 限制暫存記憶體
                    self._gpu_resource.setTempMemory(temp_memory_mb * 1024 * 1024)
                    
                    self.logger.info(f"建立 GPU 資源，記憶體限制: {self.max_memory_mb}MB，暫存: {temp_memory_mb}MB")
                    
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
            
            self.logger.info("GPU 記憶體已清除")
            
        except Exception as e:
            self.logger.error(f"清除 GPU 記憶體失敗: {e}")
    
    def log_memory_stats(self) -> None:
        """記錄記憶體統計資訊"""
        try:
            total_mb, free_mb, used_percent = self.get_gpu_memory_info()
            if total_mb > 0:
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
            query_vector = query_vector.astype('float32').reshape(1, -1)
            index = self.get_index()
            
            distances, indices = index.search(query_vector, min(k, index.ntotal))
            
            # 轉換結果
            result_distances = []
            result_ids = []
            
            for dist, idx in zip(distances[0], indices[0]):
                if idx != -1 and idx in self._id_map:  # -1 表示無效結果
                    result_distances.append(float(dist))
                    result_ids.append(self._id_map[idx])
            
            return result_distances, result_ids
            
        except Exception as e:
            self.logger.error(f"向量搜尋失敗: {e}")
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
            
            self.logger.info(f"索引已從 {file_path} 載入")
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
                        if index.load(index_file):
                            self.logger.info(f"已載入頻道 {channel_id} 的現有索引")
                        else:
                            self.logger.warning(f"載入頻道 {channel_id} 索引失敗，建立新索引")
                    
                    self._indices[channel_id] = index
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
                    self.logger.debug(f"頻道 {channel_id} 沒有向量索引")
                    return []
                
                index = self._indices[channel_id]
                distances, message_ids = index.search(query_vector, k)
                
                # 轉換距離為相似度分數（L2 距離轉換）
                results = []
                for distance, message_id in zip(distances, message_ids):
                    # L2 距離轉換為相似度分數 (0-1，越高越相似)
                    similarity = 1.0 / (1.0 + distance)
                    
                    if score_threshold is None or similarity >= score_threshold:
                        results.append((message_id, similarity))
                
                return results
                
        except Exception as e:
            self.logger.error(f"搜尋頻道 {channel_id} 向量失敗: {e}")
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