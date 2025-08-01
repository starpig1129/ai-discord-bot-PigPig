"""記憶系統配置管理模組

提供記憶系統的配置載入、驗證、硬體檢測和自動配置功能。
支援彈性的硬體資源檢測和最佳化配置選擇。
"""

import json
import logging
import platform
import psutil
import sys
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .exceptions import ConfigurationError, HardwareIncompatibleError


def _is_cuda_available() -> bool:
    """檢測 CUDA 是否可用
    
    Returns:
        bool: CUDA 是否可用
    """
    try:
        # 嘗試檢測 NVIDIA GPU
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0 and result.stdout.strip()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return False


@dataclass
class HardwareSpec:
    """硬體規格資料類別"""
    ram_gb: float
    cpu_cores: int
    gpu_available: bool = False
    gpu_memory_gb: float = 0.0
    platform: str = field(default_factory=lambda: platform.system())
    
    def __post_init__(self):
        """初始化後處理，檢測 GPU 資訊"""
        if not self.gpu_available:
            self.gpu_available, self.gpu_memory_gb = self._detect_gpu()
    
    def _detect_gpu(self) -> Tuple[bool, float]:
        """檢測 GPU 可用性和記憶體
        
        Returns:
            Tuple[bool, float]: (GPU 是否可用, GPU 記憶體 GB)
        """
        try:
            # 嘗試檢測 NVIDIA GPU
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                gpu_memory_mb = float(result.stdout.strip())
                return True, gpu_memory_mb / 1024.0
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        # 檢測 AMD GPU (ROCm)
        try:
            result = subprocess.run(['rocm-smi', '-d', '0'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return True, 0.0  # AMD GPU 存在但記憶體未知
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
            
        return False, 0.0


@dataclass
class MemoryProfile:
    """記憶系統效能配置檔案"""
    name: str = "medium_performance"
    min_ram_gb: float = 4.0
    gpu_required: bool = False
    vector_enabled: bool = True
    embedding_dimension: int = 384
    cache_size_mb: int = 512
    batch_size: int = 50
    max_concurrent_queries: int = 10
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    device: str = field(default_factory=lambda: "cuda" if _is_cuda_available() else "cpu")
    cpu_only: bool = field(default_factory=lambda: not _is_cuda_available())
    memory_threshold_mb: int = 2048
    gpu_memory_limit_mb: int = 1024  # FAISS GPU 記憶體限制（MB）
    gpu_temp_memory_mb: int = 256    # GPU 暫存記憶體限制（MB）

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryProfile':
        """從字典建立配置檔案，安全地處理缺失的鍵。"""
        # 為了獲取正確的動態預設值（如 device, cpu_only），我們先建立一個預設實例
        defaults = cls()
        
        # 使用 .get() 安全地從字典中讀取值，如果鍵不存在，則使用預設實例中的值
        return cls(
            name=data.get('name', defaults.name),
            min_ram_gb=data.get('min_ram_gb', defaults.min_ram_gb),
            gpu_required=data.get('gpu_required', defaults.gpu_required),
            vector_enabled=data.get('vector_enabled', defaults.vector_enabled),
            embedding_dimension=data.get('embedding_dimension', defaults.embedding_dimension),
            cache_size_mb=data.get('cache_size_mb', defaults.cache_size_mb),
            batch_size=data.get('batch_size', defaults.batch_size),
            max_concurrent_queries=data.get('max_concurrent_queries', defaults.max_concurrent_queries),
            embedding_model=data.get('embedding_model', defaults.embedding_model),
            device=data.get('device', defaults.device),
            cpu_only=data.get('cpu_only', defaults.cpu_only),
            memory_threshold_mb=data.get('memory_threshold_mb', defaults.memory_threshold_mb),
            gpu_memory_limit_mb=data.get('gpu_memory_limit_mb', defaults.gpu_memory_limit_mb),
            gpu_temp_memory_mb=data.get('gpu_temp_memory_mb', defaults.gpu_temp_memory_mb),
        )

    def is_compatible(self, hardware: HardwareSpec) -> bool:
        """檢查硬體是否相容此配置檔案
        
        Args:
            hardware: 硬體規格
            
        Returns:
            bool: 是否相容
        """
        if hardware.ram_gb < self.min_ram_gb:
            return False
        if self.gpu_required and not hardware.gpu_available:
            return False
        return True


class HardwareDetector:
    """硬體檢測器
    
    負責檢測系統硬體資源並推薦適合的配置檔案。
    """
    
    def __init__(self):
        """初始化硬體檢測器"""
        self.logger = logging.getLogger(__name__)
        self._hardware_spec: Optional[HardwareSpec] = None
    
    def detect_hardware(self) -> HardwareSpec:
        """檢測系統硬體規格
        
        Returns:
            HardwareSpec: 硬體規格物件
        """
        if self._hardware_spec is None:
            try:
                # 檢測記憶體
                memory = psutil.virtual_memory()
                ram_gb = memory.total / (1024**3)
                
                # 檢測 CPU 核心數
                cpu_cores = psutil.cpu_count(logical=True)
                
                self._hardware_spec = HardwareSpec(
                    ram_gb=ram_gb,
                    cpu_cores=cpu_cores
                )
                
                self.logger.info(
                    f"檢測到硬體規格: RAM {ram_gb:.1f}GB, "
                    f"CPU {cpu_cores} 核心, "
                    f"GPU {'可用' if self._hardware_spec.gpu_available else '不可用'}"
                )
                
            except Exception as e:
                self.logger.error(f"硬體檢測失敗: {e}")
                raise HardwareIncompatibleError(f"無法檢測系統硬體: {e}")
        
        return self._hardware_spec
    
    def recommend_profile(self, profiles: Dict[str, MemoryProfile]) -> str:
        """推薦適合的配置檔案
        
        Args:
            profiles: 可用的配置檔案字典
            
        Returns:
            str: 推薦的配置檔案名稱
            
        Raises:
            HardwareIncompatibleError: 無適合的配置檔案
        """
        hardware = self.detect_hardware()
        
        # 按效能從高到低排序，優先使用 Qwen3 模型
        profile_order = [
            "qwen3_high_performance",
            "qwen3_medium_performance",
            "high_performance",
            "medium_performance",
            "low_performance"
        ]
        
        for profile_name in profile_order:
            if profile_name in profiles:
                profile = profiles[profile_name]
                if profile.is_compatible(hardware):
                    self.logger.info(f"推薦配置檔案: {profile_name}")
                    return profile_name
        
        # 如果沒有相容的配置檔案，使用最低配置
        fallback_profiles = list(profiles.keys())
        if fallback_profiles:
            fallback_name = fallback_profiles[-1]
            self.logger.warning(f"硬體不足，使用備用配置: {fallback_name}")
            return fallback_name
        
        raise HardwareIncompatibleError(
            "系統硬體不符合任何配置檔案要求",
            current_spec={
                "ram_gb": hardware.ram_gb,
                "cpu_cores": hardware.cpu_cores,
                "gpu_available": hardware.gpu_available
            }
        )


class MemoryConfig:
    """記憶系統配置管理器
    
    負責載入、驗證和管理記憶系統的所有配置選項。
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化配置管理器
        
        Args:
            config_path: 配置檔案路徑，預設為 settings.json
        """
        self.logger = logging.getLogger(__name__)
        # 確保 config_path 是 Path 物件
        if config_path is None:
            self.config_path = Path("settings.json")
        elif isinstance(config_path, str):
            self.config_path = Path(config_path)
        else:
            self.config_path = config_path
        
        self.hardware_detector = HardwareDetector()
        
        # 預設配置檔案
        self.default_profiles = {
            profile_name: MemoryProfile.from_dict(profile_data)
            for profile_name, profile_data in {
                "qwen3_high_performance": {
                    "name": "qwen3_high_performance",
                    "min_ram_gb": 12.0,
                    "gpu_required": True,
                    "vector_enabled": True,
                    "embedding_dimension": 1024,
                    "cache_size_mb": 1024,
                    "batch_size": 32,
                    "max_concurrent_queries": 12,
                    "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
                    "device": "cuda" if _is_cuda_available() else "cpu",
                    "cpu_only": False,
                    "memory_threshold_mb": 4096,
                    "gpu_memory_limit_mb": 1536,
                    "gpu_temp_memory_mb": 384
                },
                "qwen3_medium_performance": {
                    "name": "qwen3_medium_performance",
                    "min_ram_gb": 8.0,
                    "gpu_required": False,
                    "vector_enabled": True,
                    "embedding_dimension": 1024,
                    "cache_size_mb": 1024,
                    "batch_size": 32,
                    "max_concurrent_queries": 12,
                    "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
                    "device": "cuda" if _is_cuda_available() else "cpu",
                    "cpu_only": not _is_cuda_available(),
                    "memory_threshold_mb": 4096,
                    "gpu_memory_limit_mb": 2048,
                    "gpu_temp_memory_mb": 512
                },
                "high_performance": {
                    "name": "high_performance",
                    "min_ram_gb": 8.0,
                    "gpu_required": True,
                    "vector_enabled": True,
                    "embedding_dimension": 768,
                    "cache_size_mb": 1024,
                    "batch_size": 100,
                    "max_concurrent_queries": 20,
                    "embedding_model": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
                    "device": "cuda" if _is_cuda_available() else "cpu",
                    "cpu_only": False,
                    "memory_threshold_mb": 4096,
                    "gpu_memory_limit_mb": 2048,
                    "gpu_temp_memory_mb": 512
                },
                "medium_performance": {
                    "name": "medium_performance",
                    "min_ram_gb": 4.0,
                    "gpu_required": False,
                    "vector_enabled": True,
                    "embedding_dimension": 384,
                    "cache_size_mb": 512,
                    "batch_size": 50,
                    "max_concurrent_queries": 10,
                    "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                    "device": "cuda" if _is_cuda_available() else "cpu",
                    "cpu_only": not _is_cuda_available(),
                    "memory_threshold_mb": 2048,
                    "gpu_memory_limit_mb": 1024,
                    "gpu_temp_memory_mb": 256
                },
                "low_performance": {
                    "name": "low_performance",
                    "min_ram_gb": 2.0,
                    "gpu_required": False,
                    "vector_enabled": False,
                    "embedding_dimension": 0,
                    "cache_size_mb": 256,
                    "batch_size": 25,
                    "max_concurrent_queries": 5,
                    "embedding_model": "",
                    "device": "cpu",
                    "cpu_only": True,
                    "memory_threshold_mb": 1024,
                    "gpu_memory_limit_mb": 512,
                    "gpu_temp_memory_mb": 128
                }
            }.items()
        }
        
        self._config: Optional[Dict[str, Any]] = None
        self._current_profile: Optional[MemoryProfile] = None
    
    def load_config(self) -> Dict[str, Any]:
        """載入配置檔案
        
        Returns:
            Dict[str, Any]: 配置資料
            
        Raises:
            ConfigurationError: 配置載入失敗
        """
        try:
            if not self.config_path.exists():
                self.logger.warning(f"配置檔案不存在: {self.config_path}")
                return self._get_default_config()
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 驗證配置
            self._validate_config(config)
            self._config = config
            
            self.logger.info(f"成功載入配置檔案: {self.config_path}")
            return config
            
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"配置檔案 JSON 格式錯誤: {e}")
        except Exception as e:
            raise ConfigurationError(f"載入配置檔案失敗: {e}")
    
    def get_memory_config(self) -> Dict[str, Any]:
        """取得記憶系統配置，並根據作業系統動態調整預設值。
        
        此方法會檢查 'max_concurrent_index_loads' 是否已設定。
        如果未設定，它會根據作業系統提供一個智慧預設值
        (Windows 為 1，其他系統為 3) 以提升穩定性，同時允許使用者手動覆寫。
    
        Returns:
            Dict[str, Any]: 記憶系統配置
        """
        if self._config is None:
            self._config = self.load_config()
        
        memory_config_data = self._config.get("memory_system", {})
        performance_config = memory_config_data.setdefault("performance", {})
    
        # 如果使用者未手動設定 max_concurrent_index_loads，則提供智慧預設值
        if 'max_concurrent_index_loads' not in performance_config:
            # 判斷作業系統來決定預設值
            default_concurrency = 1 if sys.platform == 'win32' else 3
            self.logger.info(
                f"未手動設定 'max_concurrent_index_loads'。 "
                f"根據作業系統 ({sys.platform}) 自動設定預設值為: {default_concurrency}。"
                "若需調整，請在 settings.json 的 memory_system.performance 中設定此值。"
            )
            performance_config['max_concurrent_index_loads'] = default_concurrency
            
        return memory_config_data
    
    def get_current_profile(self) -> MemoryProfile:
        """取得當前配置檔案
        
        Returns:
            MemoryProfile: 當前配置檔案
        """
        if self._current_profile is None:
            memory_config = self.get_memory_config()
            
            if memory_config.get("auto_detection", True):
                # 自動檢測並選擇配置檔案
                profile_name = self.hardware_detector.recommend_profile(self.default_profiles)
            else:
                # 使用手動指定的配置檔案
                profile_name = memory_config.get("profile", "qwen3_medium_performance")
            
            if profile_name not in self.default_profiles:
                profile_name = "qwen3_medium_performance"
            
            self._current_profile = self.default_profiles[profile_name]
            self.logger.info(f"使用配置檔案: {profile_name}")
        
        return self._current_profile
    
    def _get_default_config(self) -> Dict[str, Any]:
        """取得預設配置
        
        Returns:
            Dict[str, Any]: 預設配置
        """
        return {
            "memory_system": {
                "enabled": True,
                "auto_detection": True,
                "vector_enabled": True,
                "cpu_only_mode": False,
                "memory_threshold_mb": 2048,
                "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
                "database_path": "data/memory/memory.db",
                "index_optimization": {
                    "enabled": True,
                    "interval_hours": 24,
                    "cleanup_old_data_days": 90
                },
                "cache": {
                    "enabled": True,
                    "max_size_mb": 512,
                    "ttl_seconds": 3600
                },
                "performance": {
                    "max_concurrent_queries": 10,
                    "query_timeout_seconds": 30,
                    "batch_size": 50
                },
                "text_segmentation": {
                    "enabled": True,
                    "strategy": "hybrid",
                    "dynamic_interval": {
                        "min_minutes": 5,
                        "max_minutes": 120,
                        "base_minutes": 30,
                        "activity_multiplier": 0.2
                    },
                    "semantic_threshold": {
                        "similarity_cutoff": 0.6,
                        "min_messages_per_segment": 3,
                        "max_messages_per_segment": 50
                    },
                    "processing": {
                        "batch_size": 20,
                        "async_processing": True,
                        "background_segmentation": True
                    },
                    "quality_control": {
                        "coherence_threshold": 0.5,
                        "merge_small_segments": True,
                        "split_large_segments": True
                    }
                }
            }
        }
    
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """驗證配置檔案
        
        Args:
            config: 配置資料
            
        Raises:
            ConfigurationError: 配置驗證失敗
        """
        if "memory_system" not in config:
            raise ConfigurationError("配置檔案中缺少 memory_system 區塊")
        
        memory_config = config["memory_system"]
        
        # 驗證必要欄位
        required_fields = ["enabled"]
        for field in required_fields:
            if field not in memory_config:
                raise ConfigurationError(f"memory_system 配置中缺少必要欄位: {field}")
        
        # 驗證資料類型
        if not isinstance(memory_config["enabled"], bool):
            raise ConfigurationError("memory_system.enabled 必須為布林值")
        
        # 驗證效能設定
        if "performance" in memory_config:
            perf_config = memory_config["performance"]
            if "max_concurrent_queries" in perf_config:
                if not isinstance(perf_config["max_concurrent_queries"], int) or perf_config["max_concurrent_queries"] <= 0:
                    raise ConfigurationError("max_concurrent_queries 必須為正整數")
        
        self.logger.info("配置檔案驗證通過")
    
    def get_segmentation_config(self) -> Dict[str, Any]:
        """取得文本分割配置
        
        Returns:
            Dict[str, Any]: 分割配置
        """
        memory_config = self.get_memory_config()
        default_segmentation_config = {
            "enabled": True,
            "strategy": "hybrid",
            "dynamic_interval": {
                "min_minutes": 5,
                "max_minutes": 120,
                "base_minutes": 30,
                "activity_multiplier": 0.2
            },
            "semantic_threshold": {
                "similarity_cutoff": 0.6,
                "min_messages_per_segment": 3,
                "max_messages_per_segment": 50
            },
            "processing": {
                "batch_size": 20,
                "async_processing": True,
                "background_segmentation": True
            },
            "quality_control": {
                "coherence_threshold": 0.5,
                "merge_small_segments": True,
                "split_large_segments": True
            }
        }
        
        return memory_config.get("text_segmentation", default_segmentation_config)