"""嵌入模型服務模組

提供多語言文本嵌入向量生成功能，支援 GPU/CPU 自動切換、
批次處理優化和模型快取管理。
支援 Qwen3-Embedding 和 SentenceTransformers 模型，包含回退機制。
"""

import gc
import logging
import threading
import time
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import function as func
import asyncio

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModel
import torch.nn.functional as F

from .config import MemoryProfile
from .exceptions import VectorOperationError


class EmbeddingService:
    """嵌入模型服務
    
    負責管理嵌入模型的載入、快取和向量生成。
    支援硬體檢測後的自動配置和批次處理優化。
    支援 Qwen3-Embedding 和 SentenceTransformers 模型。
    """
    
    def __init__(self, profile: MemoryProfile):
        """初始化嵌入服務
        
        Args:
            profile: 記憶系統配置檔案
        """
        self.logger = logging.getLogger(__name__)
        self.profile = profile
        self._model: Optional[Union[SentenceTransformer, AutoModel]] = None
        self._tokenizer: Optional[AutoTokenizer] = None
        self._model_lock = threading.RLock()
        self._device = self._detect_device()
        self._cache_dir = Path("data/memory/models")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 判斷模型類型（安全檢查）
        model_name = profile.embedding_model if profile.embedding_model is not None else ""
        self._is_qwen3_model = self._is_qwen3_embedding(model_name)
        
        # 回退模型配置
        self._fallback_model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        self._using_fallback = False
        
        # 統計資訊
        self._embedding_count = 0
        self._total_processing_time = 0.0
        
        self.logger.info(
            f"嵌入服務初始化完成 - 模型: {profile.embedding_model}, "
            f"裝置: {self._device}, 維度: {profile.embedding_dimension}, "
            f"模型類型: {'Qwen3' if self._is_qwen3_model else 'SentenceTransformers'}"
        )
    
    def _is_qwen3_embedding(self, model_name: str) -> bool:
        """檢查是否為 Qwen3 embedding 模型
        
        Args:
            model_name: 模型名稱
            
        Returns:
            bool: 是否為 Qwen3 模型
        """
        if not model_name or model_name is None:
            return False
        
        try:
            model_name_str = str(model_name)
            return "Qwen3-Embedding" in model_name_str or "Qwen/Qwen3-Embedding" in model_name_str
        except (AttributeError, TypeError) as e:
            self.logger.error(f"檢查 Qwen3 模型名稱時發生錯誤: {e}")
            asyncio.create_task(func.func.report_error(e, "cogs/memory/embedding_service.py: _is_qwen3_embedding"))
            return False
    
    def _detect_device(self) -> str:
        """檢測最佳計算裝置
        
        Returns:
            str: 裝置名稱 ('cuda', 'mps', 'cpu')
        """
        if not self.profile.vector_enabled:
            return "cpu"
        
        # 強制使用 CPU 模式的檢查
        if hasattr(self.profile, 'cpu_only') and self.profile.cpu_only:
            device = "cpu"
            self.logger.info("強制使用 CPU 模式")
        # 檢測 CUDA
        elif torch.cuda.is_available():
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
    
    def _load_model(self) -> Union[SentenceTransformer, AutoModel]:
        """載入嵌入模型（支援回退機制）
        
        Returns:
            Union[SentenceTransformer, AutoModel]: 嵌入模型實例
            
        Raises:
            VectorOperationError: 模型載入失敗
        """
        if not self.profile.vector_enabled or not self.profile.embedding_model:
            raise VectorOperationError("向量功能未啟用或嵌入模型未配置")
        
        # 嘗試載入主要模型
        try:
            return self._load_primary_model()
        except Exception as e:
            self.logger.error(f"載入主要嵌入模型失敗: {e}")
            asyncio.create_task(func.func.report_error(e, "cogs/memory/embedding_service.py: _load_model"))
            
            # 嘗試載入回退模型
            if not self._using_fallback:
                try:
                    return self._load_fallback_model()
                except Exception as fallback_error:
                    self.logger.error(f"載入回退嵌入模型失敗: {fallback_error}")
                    asyncio.create_task(func.func.report_error(fallback_error, "cogs/memory/embedding_service.py: _load_model fallback"))
                    raise VectorOperationError(
                        f"主要模型和回退模型都載入失敗。"
                        f"主要模型錯誤: {e}, 回退模型錯誤: {fallback_error}"
                    )
            else:
                raise VectorOperationError(f"無法載入嵌入模型: {e}")
    
    def _load_primary_model(self) -> Union[SentenceTransformer, AutoModel]:
        """載入主要嵌入模型
        
        Returns:
            Union[SentenceTransformer, AutoModel]: 嵌入模型實例
        """
        self.logger.info(f"正在載入主要嵌入模型: {self.profile.embedding_model}")
        start_time = time.time()
        
        if self._is_qwen3_model:
            # 載入 Qwen3 模型
            model, tokenizer = self._load_qwen3_model() 
            self._tokenizer = tokenizer
        else:
            # 載入 SentenceTransformers 模型
            model = SentenceTransformer(
                self.profile.embedding_model,
                cache_folder=str(self._cache_dir),
                device=self._device
            )
        
        load_time = time.time() - start_time
        self.logger.info(f"主要模型載入完成，耗時: {load_time:.2f}秒")
        
        # 臨時設定 _model 以便測試維度
        temp_model = self._model
        self._model = model
        
        try:
            # 驗證模型維度
            test_embedding = self._encode_test_text()
            actual_dimension = test_embedding.shape[0] if test_embedding.ndim == 1 else test_embedding.shape[1]
            
            if self.profile.embedding_dimension != actual_dimension:
                self.logger.warning(
                    f"配置檔案維度 ({self.profile.embedding_dimension}) "
                    f"與實際模型維度 ({actual_dimension}) 不符，已自動調整"
                )
                self.profile.embedding_dimension = actual_dimension
        finally:
            # 恢復原來的 _model 狀態
            self._model = temp_model
        
        return model
    
    def _load_fallback_model(self) -> SentenceTransformer:
        """載入回退模型
        
        Returns:
            SentenceTransformer: 回退模型實例
        """
        self.logger.warning(f"嘗試載入回退模型: {self._fallback_model}")
        start_time = time.time()
        
        try:
            # 載入回退模型（總是使用 SentenceTransformers）
            model = SentenceTransformer(
                self._fallback_model,
                cache_folder=str(self._cache_dir),
                device=self._device
            )
            
            # 重置狀態
            self._using_fallback = True
            self._is_qwen3_model = False
            self._tokenizer = None
            
            load_time = time.time() - start_time
            self.logger.warning(
                f"回退模型載入成功，耗時: {load_time:.2f}秒。"
                f"建議檢查主要模型配置或更新 transformers 版本。"
            )
            
            # 更新維度配置
            test_embedding = model.encode(["測試"], convert_to_numpy=True)[0]
            actual_dimension = test_embedding.shape[0]
            
            if self.profile.embedding_dimension != actual_dimension:
                self.logger.warning(
                    f"使用回退模型維度: {actual_dimension} "
                    f"(原配置: {self.profile.embedding_dimension})"
                )
                self.profile.embedding_dimension = actual_dimension
            
            return model
            
        except Exception as e:
            self.logger.error(f"載入回退模型失敗: {e}")
            asyncio.create_task(func.func.report_error(e, "cogs/memory/embedding_service.py: _load_fallback_model"))
            raise VectorOperationError(f"回退模型載入失敗: {e}")
    
    def _load_qwen3_model(self) -> Tuple[AutoModel, AutoTokenizer]:
        """載入 Qwen3 嵌入模型
        
        Returns:
            Tuple[AutoModel, AutoTokenizer]: 模型和分詞器
            
        Raises:
            VectorOperationError: 載入失敗時拋出
        """
        try:
            model_name = self.profile.embedding_model
            
            # 安全檢查模型名稱
            if not model_name or model_name is None:
                raise VectorOperationError("模型名稱未設定或為空")
            
            # 安全檢查 profile 屬性
            use_instruct = False
            if hasattr(self.profile, 'use_instruct_format'):
                profile_instruct = getattr(self.profile, 'use_instruct_format', None)
                if profile_instruct is not None:
                    use_instruct = profile_instruct
            
            if use_instruct:
                self.logger.info("啟用指令格式支援")
            
            self.logger.info(f"載入 Qwen3 模型: {model_name}")
            
            # 載入分詞器並設定左填充
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                cache_dir=str(self._cache_dir),
                trust_remote_code=True
            )
            
            # 設定左填充以符合官方範例
            tokenizer.padding_side = 'left'
            
            # 如果沒有 pad_token，設定為 eos_token
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            
            # 設置環境變數以避免並行處理問題
            import os
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
            
            # 確保其他可能導致 NoneType 錯誤的環境變數也有正確值
            if "HF_HOME" not in os.environ:
                os.environ["HF_HOME"] = str(self._cache_dir)
            if "HF_HUB_CACHE" not in os.environ:
                os.environ["HF_HUB_CACHE"] = str(self._cache_dir)
            if "TRANSFORMERS_CACHE" not in os.environ:
                os.environ["TRANSFORMERS_CACHE"] = str(self._cache_dir)
            
            # 設定並行風格相關的環境變數，避免 ALL_PARALLEL_STYLES 檢查時的 NoneType 錯誤
            if "CUDA_VISIBLE_DEVICES" not in os.environ:
                os.environ["CUDA_VISIBLE_DEVICES"] = ""
            if "LOCAL_RANK" not in os.environ:
                os.environ["LOCAL_RANK"] = "-1"
            if "WORLD_SIZE" not in os.environ:
                os.environ["WORLD_SIZE"] = "1"
            if "RANK" not in os.environ:
                os.environ["RANK"] = "0"
            
            # 修復 transformers 庫的 NoneType 錯誤
            try:
                import transformers.modeling_utils
                original_post_init = transformers.modeling_utils.PreTrainedModel.post_init
                
                def safe_post_init(self):
                    # 安全地調用原始的 post_init，捕獲 NoneType 錯誤
                    try:
                        return original_post_init(self)
                    except TypeError as e:
                        if "argument of type 'NoneType' is not iterable" in str(e):
                            # 跳過並行風格檢查，直接返回
                            return
                        else:
                            raise e
                
                transformers.modeling_utils.PreTrainedModel.post_init = safe_post_init
            except ImportError as e:
                self.logger.warning(f"無法修補 PreTrainedModel.post_init: {e}")
                asyncio.create_task(func.func.report_error(e, "cogs/memory/embedding_service.py: _load_qwen3_model patch"))
                pass
            
            # 設定載入參數（相容字串類型設備）
            device_str = self._device if isinstance(self._device, str) else str(self._device)
            model_kwargs = {
                "torch_dtype": torch.float16 if device_str == "cuda" else torch.float32,
                "trust_remote_code": True,
                "use_safetensors": True,
            }
            
            # 不使用 device_map 避免 tensor parallel 錯誤
            # 改為手動移動模型到設備
            model_kwargs["device_map"] = None
            
            # 對於 Qwen3 模型，直接使用 eager attention 以避免 NoneType 錯誤
            # 不嘗試 flash_attention_2，因為它在 CPU 模式下會導致問題
            self.logger.info("使用 eager attention 以確保穩定性")
            model_kwargs["attn_implementation"] = "eager"
            
            try:
                model = AutoModel.from_pretrained(
                    model_name,
                    cache_dir=str(self._cache_dir),
                    **model_kwargs
                )
            except Exception as load_error:
                # 如果仍然失敗，嘗試不指定 attn_implementation
                self.logger.warning(f"eager attention 載入失敗: {load_error}")
                del model_kwargs["attn_implementation"]
                model = AutoModel.from_pretrained(
                    model_name,
                    cache_dir=str(self._cache_dir),
                    **model_kwargs
                )
            
            # 移動模型到指定設備
            device_str = self._device if isinstance(self._device, str) else str(self._device)
            model = model.to(self._device)
            
            model.eval()
            
            self.logger.info(f"Qwen3 模型載入成功，設備: {self._device}")
            return model, tokenizer
            
        except Exception as e:
            self.logger.error(f"無法載入 Qwen3 模型: {e}")
            asyncio.create_task(func.func.report_error(e, "cogs/memory/embedding_service.py: _load_qwen3_model"))
            raise VectorOperationError(f"無法載入 Qwen3 模型: {e}")
    
    def _encode_test_text(self) -> np.ndarray:
        """編碼測試文本以驗證模型維度
        
        Returns:
            np.ndarray: 測試嵌入向量
        """
        if self._is_qwen3_model:
            return self._encode_qwen3_batch(["測試"])[0]
        else:
            return self._model.encode(["測試"], convert_to_numpy=True)[0]
    
    def get_model(self) -> Union[SentenceTransformer, AutoModel]:
        """取得嵌入模型實例（懶載入）
        
        Returns:
            Union[SentenceTransformer, AutoModel]: 嵌入模型實例
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
            
            # 根據模型類型選擇編碼方法
            if self._is_qwen3_model:
                result = self._encode_qwen3_batch(processed_texts, show_progress)
            else:
                result = self._encode_sentence_transformers_batch(
                    processed_texts, model, show_progress
                )
            
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
            self.logger.error(f"文本編碼失敗: {e}")
            asyncio.create_task(func.func.report_error(e, "cogs/memory/embedding_service.py: encode_batch"))
            raise VectorOperationError(f"文本編碼失敗: {e}")
    
    async def encode_text_async(self, text: str) -> np.ndarray:
        """非同步編碼單一文本為向量
        
        將同步編碼工作移至背景執行緒，避免阻塞事件迴圈。
        """
        result = await asyncio.to_thread(self.encode_batch, [text])
        return result[0]
    
    async def encode_batch_async(
        self,
        texts: List[str],
        show_progress: bool = False
    ) -> np.ndarray:
        """非同步批次編碼文本為向量陣列
        
        將同步編碼工作移至背景執行緒，避免阻塞事件迴圈。
        """
        return await asyncio.to_thread(self.encode_batch, texts, show_progress)
    
    def last_token_pool(self, last_hidden_states: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        """
        使用最後一個 token 進行池化 - 根據官方範例實現
        
        Args:
            last_hidden_states: 模型的最後隱藏狀態
            attention_mask: 注意力遮罩
            
        Returns:
            池化後的嵌入向量
        """
        left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
        if left_padding:
            return last_hidden_states[:, -1]
        else:
            sequence_lengths = attention_mask.sum(dim=1) - 1
            batch_size = last_hidden_states.shape[0]
            return last_hidden_states[torch.arange(batch_size, device=last_hidden_states.device), sequence_lengths]

    def get_detailed_instruct(self, task_description: str, query: str) -> str:
        """
        格式化指令 - 根據官方範例實現
        
        Args:
            task_description: 任務描述
            query: 查詢文本
            
        Returns:
            格式化後的指令文本
        """
        return f'Instruct: {task_description}\nQuery: {query}'
    
    def _encode_qwen3_batch(
        self,
        texts: List[str],
        show_progress: bool = False
    ) -> np.ndarray:
        """使用 Qwen3 模型批次編碼文本
        
        Args:
            texts: 文本列表
            show_progress: 是否顯示進度
            
        Returns:
            np.ndarray: 嵌入向量陣列
        """
        if not texts:
            return np.array([]).reshape(0, self.profile.embedding_dimension)
        
        model = self._model
        tokenizer = self._tokenizer
        
        if model is None or tokenizer is None:
            raise VectorOperationError("Qwen3 模型或分詞器未初始化")
        
        # 分批處理
        batch_size = min(self.profile.batch_size, len(texts))
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            
            try:
                with torch.no_grad():
                    # 分詞
                    inputs = tokenizer(
                        batch_texts,
                        padding=True,
                        truncation=True,
                        max_length=512,
                        return_tensors="pt"
                    ).to(model.device)
                    
                    # 前向傳播
                    outputs = model(**inputs)
                    
                    # 使用 last_token_pool 方法 - 根據官方範例
                    last_hidden_states = outputs.last_hidden_state
                    batch_embeddings = self.last_token_pool(last_hidden_states, inputs['attention_mask'])
                    
                    # L2 正規化
                    batch_embeddings = F.normalize(batch_embeddings, p=2, dim=1)
                    
                    # 轉換為 numpy
                    batch_embeddings = batch_embeddings.cpu().numpy()
                    embeddings.append(batch_embeddings)
                    
                    # 釋放 GPU 記憶體
                    if self._device == "cuda":
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
                        
            except Exception as e:
                self.logger.error(f"Qwen3 批次編碼失敗: {e}")
                asyncio.create_task(func.func.report_error(e, "cogs/memory/embedding_service.py: _encode_qwen3_batch"))
                # 創建零向量作為回退
                fallback_embedding = np.zeros((len(batch_texts), self.profile.embedding_dimension))
                embeddings.append(fallback_embedding)
        
        # 合併結果
        if embeddings:
            return np.vstack(embeddings)
        else:
            return np.array([]).reshape(0, self.profile.embedding_dimension)
    
    def _encode_sentence_transformers_batch(
        self,
        texts: List[str],
        model: SentenceTransformer,
        show_progress: bool = False
    ) -> np.ndarray:
        """使用 SentenceTransformers 模型批次編碼文本
        
        Args:
            texts: 文本列表
            model: SentenceTransformers 模型
            show_progress: 是否顯示進度
            
        Returns:
            np.ndarray: 嵌入向量陣列
        """
        # 分批處理大量文本
        batch_size = min(self.profile.batch_size, len(texts))
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            
            with torch.no_grad():
                batch_embeddings = model.encode(
                    batch_texts,
                    convert_to_numpy=True,
                    show_progress_bar=show_progress and len(texts) > 100,
                    batch_size=min(32, len(batch_texts))  # 內部批次大小
                )
            
            embeddings.append(batch_embeddings)
            
            # 釋放 GPU 記憶體
            if self._device == "cuda":
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            elif self._device == "mps":
                # Apple Silicon MPS 記憶體清理
                if hasattr(torch.mps, 'empty_cache'):
                    torch.mps.empty_cache()
        
        # 合併結果
        return np.vstack(embeddings) if embeddings else np.array([])
    
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
    
    def get_statistics(self) -> Dict[str, Union[int, float, str, bool]]:
        """取得服務統計資訊
        
        Returns:
            Dict[str, Union[int, float, str, bool]]: 統計資訊
        """
        avg_time = (
            self._total_processing_time / self._embedding_count
            if self._embedding_count > 0 else 0.0
        )
        
        # 取得實際使用的模型名稱
        actual_model = (
            self._fallback_model if self._using_fallback
            else self.profile.embedding_model
        )
        
        return {
            "total_embeddings": self._embedding_count,
            "total_processing_time": self._total_processing_time,
            "average_time_per_embedding": avg_time,
            "configured_model": self.profile.embedding_model,
            "actual_model": actual_model,
            "using_fallback": self._using_fallback,
            "device": self._device,
            "embedding_dimension": self.profile.embedding_dimension,
            "vector_enabled": self.profile.vector_enabled,
            "is_qwen3_model": self._is_qwen3_model
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
            self.logger.error(f"模型預熱失敗: {e}")
    
    def __del__(self):
        """析構函數，清理資源"""
        try:
            self.clear_cache()
        except Exception as e:
            self.logger.error(f"清理嵌入模型時發生錯誤: {e}")
            pass
    
    def get_model_version(self) -> str:
        """取得目前使用的嵌入模型版本
        
        Returns:
            str: 模型名稱
        """
        if self._using_fallback:
            return self._fallback_model
        return self.profile.embedding_model
    
    def cleanup(self) -> None:
        """清理嵌入服務資源和快取
        
        執行完整的清理作業，釋放模型記憶體和相關資源。
        """
        try:
            self.logger.info("開始嵌入服務清理...")
            
            # 清除模型快取
            self.clear_cache()
            
            # 清理分詞器
            if hasattr(self, '_tokenizer') and self._tokenizer is not None:
                try:
                    del self._tokenizer
                    self._tokenizer = None
                except Exception as e:
                    self.logger.warning(f"清理分詞器失敗: {e}")
            
            # 重置統計資料
            self._embedding_count = 0
            self._total_processing_time = 0.0
            
            # 額外的 GPU 記憶體清理
            try:
                if self._device == "cuda":
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
                        self.logger.info("GPU 記憶體已清理")
            except Exception as e:
                self.logger.warning(f"清理 GPU 記憶體失敗: {e}")
            
            # 強制垃圾回收
            import gc
            gc.collect()
            
            self.logger.info("嵌入服務清理完成")
            
        except Exception as e:
            self.logger.error(f"清理嵌入服務時發生錯誤: {e}")


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