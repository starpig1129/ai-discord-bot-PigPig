"""重排序服務模組

提供基於 Qwen3-Reranker 的搜尋結果重排序功能。
支援多種重排序策略和效能優化。
根據官方範例實作正確的載入和評分邏輯。
"""

import logging
import os
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

# 在模組載入時就設定環境變數，避免 NoneType 錯誤
if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = str(Path("data/memory/models"))
if "HF_HUB_CACHE" not in os.environ:
    os.environ["HF_HUB_CACHE"] = str(Path("data/memory/models"))
if "TRANSFORMERS_CACHE" not in os.environ:
    os.environ["TRANSFORMERS_CACHE"] = str(Path("data/memory/models"))

# 設定並行風格相關的環境變數，避免 ALL_PARALLEL_STYLES 檢查時的 NoneType 錯誤

if "LOCAL_RANK" not in os.environ:
    os.environ["LOCAL_RANK"] = "-1"
if "WORLD_SIZE" not in os.environ:
    os.environ["WORLD_SIZE"] = "1"
if "RANK" not in os.environ:
    os.environ["RANK"] = "0"

# 設置 tokenizers 並行處理
if "TOKENIZERS_PARALLELISM" not in os.environ:
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch.nn.functional as F

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
except ImportError:
    pass

from .config import MemoryProfile
from .exceptions import VectorOperationError


class RerankerService:
    """重排序服務
    
    負責管理重排序模型的載入、快取和重排序處理。
    專為 Qwen3-Reranker-0.6B 模型優化，使用官方範例的實作方式。
    """
    
    def __init__(self, profile: MemoryProfile, reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"):
        """初始化重排序服務
        
        Args:
            profile: 記憶系統配置檔案
            reranker_model: 重排序模型名稱
        """
        self.logger = logging.getLogger(__name__)
        self.profile = profile
        self.reranker_model = reranker_model
        self._model: Optional[AutoModelForCausalLM] = None
        self._tokenizer: Optional[AutoTokenizer] = None
        self._model_lock = threading.RLock()
        self._device = self._detect_device()
        self._cache_dir = Path("data/memory/models")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Qwen3 Reranker 專用 token IDs（根據官方範例）
        self._token_true_id: Optional[int] = None
        self._token_false_id: Optional[int] = None
        self._prefix_tokens: Optional[List[int]] = None
        self._suffix_tokens: Optional[List[int]] = None
        
        # 重排序參數（根據官方範例）
        self.max_length = 8192  # 官方範例使用的最大長度
        self.max_candidates = 100  # 最大重排序候選數量
        
        # 官方 prompt 格式
        self.prompt_prefix = (
            "<|im_start|>system\n"
            "Judge whether the Document meets the requirements based on the Query and the Instruct provided. "
            "Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n"
            "<|im_start|>user\n"
        )
        self.prompt_suffix = (
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
            "<think>\n\n</think>\n\n"
        )
        
        # 統計資訊
        self._rerank_count = 0
        self._total_processing_time = 0.0
        
        self.logger.info(
            f"重排序服務初始化完成 - 模型: {reranker_model}, "
            f"裝置: {self._device}"
        )
    
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
    
    def _load_model(self) -> Tuple[AutoModelForCausalLM, AutoTokenizer]:
        """載入重排序模型（使用官方範例的載入方式）
        
        Returns:
            Tuple[AutoModelForCausalLM, AutoTokenizer]: 模型和分詞器
            
        Raises:
            VectorOperationError: 模型載入失敗
        """
        if not self.profile.vector_enabled or not self.reranker_model:
            raise VectorOperationError("向量功能未啟用或模型名稱為空")
        
        try:
            self.logger.info(f"正在載入重排序模型: {self.reranker_model}")
            start_time = time.time()
            
            # 安全檢查模型名稱
            model_name = str(self.reranker_model) if self.reranker_model is not None else "Qwen/Qwen3-Reranker-0.6B"
            
            # 載入分詞器
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                cache_dir=str(self._cache_dir),
                trust_remote_code=True,
                padding_side='left'  # 官方範例設定
            )
            
            # 載入模型
            model_kwargs = {
                "cache_dir": str(self._cache_dir),
                "trust_remote_code": True
            }

            use_device_map_auto = False
            if self._device == "cuda":
                torch_version = torch.__version__
                major, minor = map(int, torch_version.split('.')[:2])
                
                if major > 2 or (major == 2 and minor >= 5):
                    use_device_map_auto = True # 標記將使用 device_map
                    model_kwargs.update({
                        "torch_dtype": torch.float16,
                        "device_map": "auto"
                    })
                else:
                    # PyTorch < 2.5，將先載入到 CPU，然後手動移至 CUDA
                    model_kwargs.update({
                        "torch_dtype": torch.float16
                    })
            else: # "mps" 或 "cpu"
                model_kwargs.update({
                    "torch_dtype": torch.float32 #  或者為 MPS 選擇合適的 dtype
                })
            
            model = AutoModelForCausalLM.from_pretrained(
                model_name, **model_kwargs
            )
            
            # 移動到指定設備
            if not use_device_map_auto:
                model = model.to(self._device)
            
            model.eval()
            
            # 初始化 token IDs
            try:
                self._token_false_id = tokenizer.convert_tokens_to_ids("no")
                self._token_true_id = tokenizer.convert_tokens_to_ids("yes")
                
                # 安全檢查 unk_token_id
                unk_token_id = getattr(tokenizer, 'unk_token_id', None)
                
                # 檢查 token IDs 是否有效
                if (self._token_false_id is None or self._token_true_id is None or
                    (unk_token_id is not None and
                     (self._token_false_id == unk_token_id or self._token_true_id == unk_token_id))):
                    raise VectorOperationError("無法找到有效的 'yes' 或 'no' token ID")
                    
            except Exception as e:
                raise VectorOperationError(f"初始化 token IDs 失敗: {e}")
            
            # 預處理 prefix 和 suffix tokens（官方範例方式）
            try:
                prefix_text = self.prompt_prefix if self.prompt_prefix is not None else ""
                suffix_text = self.prompt_suffix if self.prompt_suffix is not None else ""
                self._prefix_tokens = tokenizer.encode(prefix_text, add_special_tokens=False)
                self._suffix_tokens = tokenizer.encode(suffix_text, add_special_tokens=False)
            except Exception as e:
                self.logger.warning(f"預處理 prompt tokens 失敗: {e}")
                self._prefix_tokens = []
                self._suffix_tokens = []
            
            load_time = time.time() - start_time
            # 確保 load_time 是數值類型
            if isinstance(load_time, (int, float)):
                load_time_str = f"{load_time:.2f}"
            else:
                load_time_str = str(load_time)
            
            self.logger.info(
                f"重排序模型載入完成，耗時: {load_time_str}秒, "
                f"設備: {next(model.parameters()).device}, "
                f"Token IDs - yes: {self._token_true_id}, no: {self._token_false_id}"
            )
            
            return model, tokenizer
            
        except Exception as e:
            error_message = str(e) if e is not None else "未知錯誤"
            self.logger.error(f"載入重排序模型失敗: {error_message}")
            raise VectorOperationError(f"無法載入重排序模型 {model_name}: {error_message}")
    
    def get_model(self) -> Tuple[AutoModelForCausalLM, AutoTokenizer]:
        """取得重排序模型實例（懶載入）
        
        Returns:
            Tuple[AutoModelForCausalLM, AutoTokenizer]: 模型和分詞器
        """
        if self._model is None or self._tokenizer is None:
            with self._model_lock:
                if self._model is None or self._tokenizer is None:
                    self._model, self._tokenizer = self._load_model()
        return self._model, self._tokenizer
    
    def format_instruction(self, instruction: Optional[str], query: str, doc: str) -> str:
        """格式化指令（根據官方範例）
        
        Args:
            instruction: 指令文本，若為 None 則使用預設指令
            query: 查詢文本
            doc: 文檔內容
            
        Returns:
            str: 格式化後的指令
        """
        if instruction is None:
            instruction = 'Given a web search query, retrieve relevant passages that answer the query'
        
        output = "<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}".format(
            instruction=instruction, query=query, doc=doc
        )
        return output
    
    def process_inputs(self, pairs: List[str]) -> Dict[str, torch.Tensor]:
        """處理輸入文本對（根據官方範例的 process_inputs 函數）
        
        Args:
            pairs: 格式化後的文本對列表
            
        Returns:
            Dict[str, torch.Tensor]: 處理後的輸入張量
        """
        model, tokenizer = self.get_model()
        
        # 計算最大內容長度（安全檢查）
        prefix_len = len(self._prefix_tokens) if self._prefix_tokens is not None else 0
        suffix_len = len(self._suffix_tokens) if self._suffix_tokens is not None else 0
        max_content_length = self.max_length - prefix_len - suffix_len
        
        # 確保最大長度合理
        if max_content_length <= 0:
            max_content_length = min(self.max_length // 2, 4096)
        
        # 分詞處理（不包含 padding）
        inputs = tokenizer(
            pairs, 
            padding=False, 
            truncation='longest_first',
            return_attention_mask=False, 
            max_length=max_content_length
        )
        
        # 添加 prefix 和 suffix tokens（安全檢查）
        for i, input_ids in enumerate(inputs['input_ids']):
            prefix_tokens = self._prefix_tokens if self._prefix_tokens is not None else []
            suffix_tokens = self._suffix_tokens if self._suffix_tokens is not None else []
            inputs['input_ids'][i] = prefix_tokens + input_ids + suffix_tokens
        
        # 統一 padding 和轉換為張量
        inputs = tokenizer.pad(
            inputs, 
            padding=True, 
            return_tensors="pt", 
            max_length=self.max_length
        )
        
        # 移動到模型設備
        for key in inputs:
            inputs[key] = inputs[key].to(model.device)
        
        return inputs
    
    @torch.no_grad()
    def compute_logits(self, inputs: Dict[str, torch.Tensor]) -> List[float]:
        """計算 logits 分數（根據官方範例的 compute_logits 函數）
        
        Args:
            inputs: 處理後的輸入張量
            
        Returns:
            List[float]: 分數列表
        """
        model, _ = self.get_model()
        
        # 前向傳播
        batch_scores = model(**inputs).logits[:, -1, :]
        
        # 提取 yes/no token 的 logits
        true_vector = batch_scores[:, self._token_true_id]
        false_vector = batch_scores[:, self._token_false_id]
        
        # 構建 [false, true] 的分數矩陣
        batch_scores = torch.stack([false_vector, true_vector], dim=1)
        
        # 應用 log_softmax
        batch_scores = F.log_softmax(batch_scores, dim=1)
        
        # 取 true（yes）的分數並轉換為機率
        scores = batch_scores[:, 1].exp().tolist()
        
        return scores
    
    def rerank_results(
        self, 
        query: str, 
        candidates: List[Dict], 
        score_field: str = "content",
        top_k: Optional[int] = None,
        instruction: Optional[str] = None
    ) -> List[Dict]:
        """重排序搜尋結果
        
        Args:
            query: 查詢文本
            candidates: 候選結果列表，每個項目包含文本內容
            score_field: 用於重排序的文本欄位名稱
            top_k: 返回前 k 個結果，None 表示返回全部
            instruction: 自定義指令，None 表示使用預設指令
            
        Returns:
            List[Dict]: 重排序後的結果列表，包含新的 rerank_score
        """
        if not candidates:
            return candidates
        
        if not self.profile.vector_enabled:
            self.logger.debug("向量功能未啟用，跳過重排序")
            return candidates
        
        try:
            start_time = time.time()
            
            # 限制候選數量以控制計算成本
            raw_candidates = candidates[:self.max_candidates]
            
            # 提取候選文本 - 添加類型安全檢查
            candidate_texts = []
            valid_candidates = []
            for i, candidate in enumerate(raw_candidates):
                # 確保候選項目是字典類型
                if not isinstance(candidate, dict):
                    self.logger.warning(f"候選項目 {i} 不是字典類型: {type(candidate)}, 跳過")
                    continue
                
                valid_candidates.append(candidate)
                text = candidate.get(score_field, "")
                if isinstance(text, str):
                    candidate_texts.append(text)
                else:
                    # 如果不是字串，嘗試轉換
                    candidate_texts.append(str(text))
            
            # 如果沒有有效的候選項目，返回原始結果
            if not valid_candidates:
                self.logger.warning("沒有有效的候選項目，返回原始結果")
                return candidates
            
            # 計算重排序分數
            rerank_scores = self._compute_rerank_scores(query, candidate_texts, instruction)
            
            # 添加重排序分數到候選結果
            limited_candidates = []
            for i, candidate in enumerate(valid_candidates):
                candidate = candidate.copy()  # 避免修改原始資料
                candidate["rerank_score"] = float(rerank_scores[i]) if i < len(rerank_scores) else 0.0
                limited_candidates.append(candidate)
            
            # 按重排序分數排序
            reranked_results = sorted(
                limited_candidates, 
                key=lambda x: x.get("rerank_score", 0.0), 
                reverse=True
            )
            
            # 限制返回結果數量
            if top_k is not None:
                reranked_results = reranked_results[:top_k]
            
            # 更新統計
            processing_time = time.time() - start_time
            self._rerank_count += len(limited_candidates)
            self._total_processing_time += processing_time
            
            # 確保時間變量是數值類型
            if isinstance(processing_time, (int, float)):
                time_str = f"{processing_time:.2f}"
                avg_time = processing_time / len(limited_candidates) * 1000
                avg_str = f"{avg_time:.1f}" if isinstance(avg_time, (int, float)) else str(avg_time)
            else:
                time_str = str(processing_time)
                avg_str = "N/A"
            
            self.logger.debug(
                f"重排序完成: {len(limited_candidates)} 個候選, "
                f"耗時: {time_str}秒, "
                f"平均: {avg_str}ms/項目"
            )
            
            return reranked_results
            
        except Exception as e:
            self.logger.error(f"重排序失敗: {e}")
            # 降級處理：返回原始結果
            return candidates
    
    def _compute_rerank_scores(
        self, 
        query: str, 
        candidate_texts: List[str], 
        instruction: Optional[str] = None
    ) -> List[float]:
        """計算重排序分數（使用官方範例的邏輯）
        
        Args:
            query: 查詢文本
            candidate_texts: 候選文本列表
            instruction: 自定義指令
            
        Returns:
            List[float]: 重排序分數列表
        """
        if not candidate_texts:
            return []
        
        try:
            # 準備格式化的輸入對
            pairs = []
            for text in candidate_texts:
                formatted_input = self.format_instruction(instruction, query, text)
                pairs.append(formatted_input)
            
            # 分批處理（考慮記憶體限制）
            batch_size = min(4, len(pairs))  # Reranker 使用較小的批次大小
            all_scores = []
            
            for i in range(0, len(pairs), batch_size):
                batch_pairs = pairs[i:i + batch_size]
                
                # 處理輸入
                inputs = self.process_inputs(batch_pairs)
                
                # 計算分數
                batch_scores = self.compute_logits(inputs)
                all_scores.extend(batch_scores)
                
                # 釋放記憶體
                if self._device == "cuda":
                    torch.cuda.empty_cache()
            
            return all_scores
            
        except Exception as e:
            self.logger.error(f"計算重排序分數失敗: {e}")
            # 返回預設分數
            return [0.0] * len(candidate_texts)
    
    def get_statistics(self) -> Dict[str, Union[int, float, str]]:
        """取得重排序服務統計資訊
        
        Returns:
            Dict[str, Union[int, float, str]]: 統計資訊
        """
        avg_time = (
            self._total_processing_time / self._rerank_count 
            if self._rerank_count > 0 else 0.0
        )
        
        return {
            "total_reranks": self._rerank_count,
            "total_processing_time": self._total_processing_time,
            "average_time_per_rerank": avg_time,
            "reranker_model": self.reranker_model,
            "device": self._device,
            "max_candidates": self.max_candidates,
            "max_length": self.max_length,
            "token_true_id": self._token_true_id,
            "token_false_id": self._token_false_id
        }
    
    def clear_cache(self) -> None:
        """清除模型快取並釋放記憶體"""
        with self._model_lock:
            if self._model is not None:
                del self._model
                self._model = None
                
            if self._tokenizer is not None:
                del self._tokenizer
                self._tokenizer = None
                
            # 重置相關變數
            self._token_true_id = None
            self._token_false_id = None
            self._prefix_tokens = None
            self._suffix_tokens = None
                
            # 強制垃圾回收
            import gc
            gc.collect()
            
            # 清除 GPU 快取
            if self._device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            self.logger.info("重排序模型快取已清除")
    
    def warmup(self) -> None:
        """預熱模型（載入並進行測試推理）"""
        try:
            self.logger.info("正在預熱重排序模型...")
            start_time = time.time()
            
            # 測試重排序
            test_query = "測試查詢"
            test_candidates = [
                {"content": "相關測試內容"},
                {"content": "不相關測試內容"}
            ]
            
            self.rerank_results(test_query, test_candidates)
            
            warmup_time = time.time() - start_time
            # 確保 warmup_time 是數值類型
            if isinstance(warmup_time, (int, float)):
                warmup_time_str = f"{warmup_time:.2f}"
            else:
                warmup_time_str = str(warmup_time)
            
            self.logger.info(f"重排序模型預熱完成，耗時: {warmup_time_str}秒")
            
        except Exception as e:
            self.logger.warning(f"重排序模型預熱失敗: {e}")
    
    def __del__(self):
        """析構函數，清理資源"""
        try:
            self.clear_cache()
        except Exception:
            pass


class RerankerServiceManager:
    """重排序服務管理器
    
    管理重排序服務實例，提供服務池和資源管理。
    """
    
    def __init__(self):
        """初始化服務管理器"""
        self.logger = logging.getLogger(__name__)
        self._services: Dict[str, RerankerService] = {}
        self._lock = threading.RLock()
    
    def get_service(
        self, 
        profile: MemoryProfile, 
        reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    ) -> RerankerService:
        """取得重排序服務實例
        
        Args:
            profile: 記憶系統配置檔案
            reranker_model: 重排序模型名稱
            
        Returns:
            RerankerService: 重排序服務實例
        """
        service_key = f"{profile.name}_{reranker_model}"
        
        if service_key not in self._services:
            with self._lock:
                if service_key not in self._services:
                    self._services[service_key] = RerankerService(profile, reranker_model)
        
        return self._services[service_key]
    
    def clear_all_caches(self) -> None:
        """清除所有服務的快取"""
        with self._lock:
            for service in self._services.values():
                service.clear_cache()
            self._services.clear()
            self.logger.info("所有重排序服務快取已清除")
    
    def get_all_statistics(self) -> Dict[str, Dict[str, Union[int, float, str]]]:
        """取得所有服務的統計資訊
        
        Returns:
            Dict[str, Dict[str, Union[int, float, str]]]: 服務統計資訊
        """
        return {
            service_key: service.get_statistics()
            for service_key, service in self._services.items()
        }


# 全域重排序服務管理器實例
reranker_service_manager = RerankerServiceManager()