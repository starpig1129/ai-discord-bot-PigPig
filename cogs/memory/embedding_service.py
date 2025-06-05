"""嵌入模型服務模組

提供多語言文本嵌入向量生成功能，支援 GPU/CPU 自動切換、
批次處理優化和模型快取管理。
"""

import gc
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from .config import MemoryProfile
from .exceptions import VectorOperationError


class EmbeddingService:
    """嵌入模型服務
    
    負責管理嵌入模型的載入、快取和向量生成。
    支援硬體檢測後的自動配置和批次處理優化。
    """
    
    def __init__(self, profile: MemoryProfile):
        """初始化嵌入服務
        
        Args:
            profile: 記憶系統配置檔案
        """
        self.logger = logging.getLogger(__name__)
        self.profile = profile
        self._model: Optional[SentenceTransformer] = None
        self._model_lock = threading.RLock()
        self._device = self._detect_device()
        self._cache_dir = Path("data/memory/models")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 統計資訊
        self._embedding_count = 0
        self._total_processing_time = 0.0
        
        self.logger.info(
            f"嵌入服務初始化完成 - 模型: {profile.embedding_model}, "
            f"裝置: {self._device}, 維度: {profile.embedding_dimension}"
        )
    
    def _detect_device(self) -> str:
        """檢測最佳計算裝置
        
        Returns:
            str: 裝置名稱 ('cuda', 'mps', 'cpu')
        """
        if not self.profile.vector_enabled:
            return "cpu"
        
        # 檢測 CUDA
        if torch.cuda.is_available() and not self.profile.gpu_required is False:
            device = "cuda"
            self.logger.info(f"使用 CUDA GPU: {torch.cuda.get_device_name()}")
        # 檢測 Apple Silicon MPS
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device = "mps"
            self.logger.info("使用 Apple Silicon MPS")
        else:
            device = "cpu"
            self.logger.info("使用 CPU")
        
        return device
    
    def _load_model(self) -> SentenceTransformer:
        """載入嵌入模型
        
        Returns:
            SentenceTransformer: 嵌入模型實例
            
        Raises:
            VectorOperationError: 模型載入失敗
        """
        if not self.profile.vector_enabled or not self.profile.embedding_model:
            raise VectorOperationError("向量功能未啟用或嵌入模型未配置")
        
        try:
            self.logger.info(f"正在載入嵌入模型: {self.profile.embedding_model}")
            start_time = time.time()
            
            model = SentenceTransformer(
                self.profile.embedding_model,
                cache_folder=str(self._cache_dir),
                device=self._device
            )
            
            load_time = time.time() - start_time
            self.logger.info(f"模型載入完成，耗時: {load_time:.2f}秒")
            
            # 驗證模型維度
            test_embedding = model.encode(["測試"], convert_to_numpy=True)
            actual_dimension = test_embedding.shape[1]
            
            if self.profile.embedding_dimension != actual_dimension:
                self.logger.warning(
                    f"配置檔案維度 ({self.profile.embedding_dimension}) "
                    f"與實際模型維度 ({actual_dimension}) 不符，已自動調整"
                )
                self.profile.embedding_dimension = actual_dimension
            
            return model
            
        except Exception as e:
            self.logger.error(f"載入嵌入模型失敗: {e}")
            raise VectorOperationError(f"無法載入嵌入模型 {self.profile.embedding_model}: {e}")
    
    def get_model(self) -> SentenceTransformer:
        """取得嵌入模型實例（懶載入）
        
        Returns:
            SentenceTransformer: 嵌入模型實例
        """
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    self._model = self._load_model()
        return self._model
    
    def encode_text(self, text: str) -> np.ndarray:
        """編碼單一文本為向量
        
        Args:
            text: 輸入文本
            
        Returns:
            np.ndarray: 嵌入向量
            
        Raises:
            VectorOperationError: 編碼失敗
        """
        return self.encode_batch([text])[0]
    
    def encode_batch(
        self, 
        texts: List[str], 
        show_progress: bool = False
    ) -> np.ndarray:
        """批次編碼文本為向量陣列
        
        Args:
            texts: 文本列表
            show_progress: 是否顯示進度
            
        Returns:
            np.ndarray: 嵌入向量陣列，形狀為 (len(texts), embedding_dimension)
            
        Raises:
            VectorOperationError: 編碼失敗
        """
        if not texts:
            return np.array([]).reshape(0, self.profile.embedding_dimension)
        
        if not self.profile.vector_enabled:
            raise VectorOperationError("向量功能未啟用")
        
        try:
            start_time = time.time()
            model = self.get_model()
            
            # 預處理文本
            processed_texts = [self._preprocess_text(text) for text in texts]
            
            # 分批處理大量文本
            batch_size = min(self.profile.batch_size, len(processed_texts))
            embeddings = []
            
            for i in range(0, len(processed_texts), batch_size):
                batch_texts = processed_texts[i:i + batch_size]
                
                with torch.no_grad():
                    batch_embeddings = model.encode(
                        batch_texts,
                        convert_to_numpy=True,
                        show_progress_bar=show_progress and len(processed_texts) > 100,
                        batch_size=min(32, len(batch_texts))  # 內部批次大小
                    )
                
                embeddings.append(batch_embeddings)
                
                # 釋放 GPU 記憶體
                if self._device != "cpu":
                    torch.cuda.empty_cache() if self._device == "cuda" else None
            
            # 合併結果
            result = np.vstack(embeddings) if embeddings else np.array([])
            
            # 更新統計
            processing_time = time.time() - start_time
            self._embedding_count += len(texts)
            self._total_processing_time += processing_time
            
            self.logger.debug(
                f"批次編碼完成: {len(texts)} 個文本, "
                f"耗時: {processing_time:.2f}秒, "
                f"平均: {processing_time/len(texts)*1000:.1f}ms/文本"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"批次編碼失敗: {e}")
            raise VectorOperationError(f"文本編碼失敗: {e}")
    
    def _preprocess_text(self, text: str) -> str:
        """預處理文本
        
        Args:
            text: 原始文本
            
        Returns:
            str: 處理後的文本
        """
        if not text or not isinstance(text, str):
            return ""
        
        # 去除多餘空白
        text = " ".join(text.split())
        
        # 限制文本長度（避免過長文本影響性能）
        max_length = 512
        if len(text) > max_length:
            text = text[:max_length]
            self.logger.debug(f"文本已截斷至 {max_length} 字元")
        
        return text
    
    def get_embedding_dimension(self) -> int:
        """取得嵌入向量維度
        
        Returns:
            int: 向量維度
        """
        return self.profile.embedding_dimension
    
    def get_statistics(self) -> Dict[str, Union[int, float, str]]:
        """取得服務統計資訊
        
        Returns:
            Dict[str, Union[int, float, str]]: 統計資訊
        """
        avg_time = (
            self._total_processing_time / self._embedding_count 
            if self._embedding_count > 0 else 0.0
        )
        
        return {
            "total_embeddings": self._embedding_count,
            "total_processing_time": self._total_processing_time,
            "average_time_per_embedding": avg_time,
            "model_name": self.profile.embedding_model,
            "device": self._device,
            "embedding_dimension": self.profile.embedding_dimension,
            "vector_enabled": self.profile.vector_enabled
        }
    
    def clear_cache(self) -> None:
        """清除模型快取並釋放記憶體"""
        with self._model_lock:
            if self._model is not None:
                del self._model
                self._model = None
                
            # 強制垃圾回收
            gc.collect()
            
            # 清除 GPU 快取
            if self._device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            self.logger.info("嵌入模型快取已清除")
    
    def warmup(self) -> None:
        """預熱模型（載入並進行測試推理）"""
        try:
            self.logger.info("正在預熱嵌入模型...")
            start_time = time.time()
            
            # 載入模型並進行測試推理
            test_texts = ["Hello, world!", "你好，世界！", "こんにちは、世界！"]
            self.encode_batch(test_texts)
            
            warmup_time = time.time() - start_time
            self.logger.info(f"模型預熱完成，耗時: {warmup_time:.2f}秒")
            
        except Exception as e:
            self.logger.warning(f"模型預熱失敗: {e}")
    
    def __del__(self):
        """析構函數，清理資源"""
        try:
            self.clear_cache()
        except Exception:
            pass


class EmbeddingServiceManager:
    """嵌入服務管理器
    
    管理多個配置檔案的嵌入服務實例，提供服務池和資源管理。
    """
    
    def __init__(self):
        """初始化服務管理器"""
        self.logger = logging.getLogger(__name__)
        self._services: Dict[str, EmbeddingService] = {}
        self._lock = threading.RLock()
    
    def get_service(self, profile: MemoryProfile) -> EmbeddingService:
        """取得嵌入服務實例
        
        Args:
            profile: 記憶系統配置檔案
            
        Returns:
            EmbeddingService: 嵌入服務實例
        """
        service_key = f"{profile.name}_{profile.embedding_model}"
        
        if service_key not in self._services:
            with self._lock:
                if service_key not in self._services:
                    self._services[service_key] = EmbeddingService(profile)
        
        return self._services[service_key]
    
    def clear_all_caches(self) -> None:
        """清除所有服務的快取"""
        with self._lock:
            for service in self._services.values():
                service.clear_cache()
            self._services.clear()
            self.logger.info("所有嵌入服務快取已清除")
    
    def get_all_statistics(self) -> Dict[str, Dict[str, Union[int, float, str]]]:
        """取得所有服務的統計資訊
        
        Returns:
            Dict[str, Dict[str, Union[int, float, str]]]: 服務統計資訊
        """
        return {
            service_key: service.get_statistics()
            for service_key, service in self._services.items()
        }


# 全域服務管理器實例
embedding_service_manager = EmbeddingServiceManager()