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


class VectorIndex:
    """向量索引封裝類別
    
    封裝 FAISS 索引的基本操作，提供統一的介面。
    """
    
    def __init__(
        self, 
        dimension: int, 
        index_type: str = "Flat",
        metric: str = "L2",
        use_gpu: bool = False
    ):
        """初始化向量索引
        
        Args:
            dimension: 向量維度
            index_type: 索引類型 ("Flat", "IVFFlat", "HNSW" 等)
            metric: 距離度量 ("L2", "IP")
            use_gpu: 是否使用 GPU
        """
        self.dimension = dimension
        self.index_type = index_type
        self.metric = metric
        self.use_gpu = use_gpu
        self._index: Optional[faiss.Index] = None
        self._gpu_index: Optional[faiss.Index] = None
        self._id_map: Dict[int, str] = {}  # FAISS ID -> 實際 ID 映射
        self._reverse_id_map: Dict[str, int] = {}  # 實際 ID -> FAISS ID 映射
        self._next_id = 0
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
            
            # 嘗試移至 GPU
            if self.use_gpu and faiss.get_num_gpus() > 0:
                try:
                    gpu_resource = faiss.StandardGpuResources()
                    self._gpu_index = faiss.index_cpu_to_gpu(gpu_resource, 0, self._index)
                    self.logger.info(f"索引已移至 GPU")
                except Exception as e:
                    self.logger.warning(f"無法將索引移至 GPU: {e}")
                    self._gpu_index = None
        
        return self._gpu_index if self._gpu_index is not None else self._index
    
    def add_vectors(self, vectors: np.ndarray, ids: List[str]) -> bool:
        """新增向量到索引
        
        Args:
            vectors: 向量陣列，形狀為 (n, dimension)
            ids: 對應的 ID 列表
            
        Returns:
            bool: 是否成功
        """
        try:
            if len(vectors) != len(ids):
                raise ValueError("向量數量與 ID 數量不符")
            
            # 轉換為 float32
            vectors = vectors.astype('float32')
            
            # 建立 ID 映射
            faiss_ids = []
            for id_str in ids:
                if id_str not in self._reverse_id_map:
                    faiss_id = self._next_id
                    self._id_map[faiss_id] = id_str
                    self._reverse_id_map[id_str] = faiss_id
                    self._next_id += 1
                    faiss_ids.append(faiss_id)
                else:
                    # 已存在的向量，跳過或更新
                    self.logger.debug(f"向量 ID {id_str} 已存在，跳過")
                    continue
            
            if faiss_ids:
                index = self.get_index()
                index.add(vectors[:len(faiss_ids)])
                self.logger.debug(f"新增 {len(faiss_ids)} 個向量到索引")
            
            return True
            
        except Exception as e:
            self.logger.error(f"新增向量失敗: {e}")
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
            
            # 儲存 FAISS 索引
            index = self._index  # 使用 CPU 索引進行儲存
            if index is not None:
                faiss.write_index(index, str(file_path))
                
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
                
                self.logger.info(f"索引已儲存到: {file_path}")
                return True
            
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
            
            # 嘗試移至 GPU
            if self.use_gpu and faiss.get_num_gpus() > 0:
                try:
                    gpu_resource = faiss.StandardGpuResources()
                    self._gpu_index = faiss.index_cpu_to_gpu(gpu_resource, 0, self._index)
                except Exception as e:
                    self.logger.warning(f"無法將載入的索引移至 GPU: {e}")
            
            self.logger.info(f"索引已從 {file_path} 載入")
            return True
            
        except Exception as e:
            self.logger.error(f"載入索引失敗: {e}")
            return False


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
        
        self.logger.info(
            f"向量管理器初始化 - GPU: {self.use_gpu}, "
            f"維度: {profile.embedding_dimension}"
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
                        use_gpu=self.use_gpu
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
        message_ids: List[str]
    ) -> bool:
        """新增向量到頻道索引
        
        Args:
            channel_id: 頻道 ID
            vectors: 向量陣列
            message_ids: 對應的訊息 ID 列表
            
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
                success = index.add_vectors(vectors, message_ids)
                
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
                for message_id, distance in zip(message_ids, distances):
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
            self._indices.clear()
            
        # 強制垃圾回收
        gc.collect()
        
        self.logger.info("向量管理器快取已清除")
    
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