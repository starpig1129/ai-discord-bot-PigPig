"""
優化配置管理模組

提供統一的配置載入、驗證和管理功能，支援環境特定配置和動態更新。
"""

import json
import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
from function import func

logger = logging.getLogger(__name__)

@dataclass
class OptimizationSettings:
    """優化設定資料結構"""
    # Gemini 快取設定
    enable_gemini_cache: bool = True
    gemini_cache_ttl: str = "3600s"
    gemini_max_cache_count: int = 50
    
    # 處理快取設定
    enable_processing_cache: bool = True
    processing_cache_ttl: int = 300
    processing_max_cache_size: int = 1000
    
    # 記憶快取設定
    enable_memory_cache: bool = True
    memory_cache_ttl: int = 1800
    memory_max_search_results: int = 100
    
    # 並行工具設定
    enable_parallel_tools: bool = True
    max_parallel_workers: int = 4
    tool_default_timeout: float = 30.0
    
    # 性能監控設定
    enable_performance_monitoring: bool = True
    performance_max_history: int = 1000
    
    # 自動清理設定
    auto_cleanup_interval: int = 3600
    enable_auto_cleanup: bool = True
    
    # 降級設定
    enable_graceful_degradation: bool = True
    fallback_timeout: float = 5.0
    max_retry_attempts: int = 3
    
    # 工具超時覆寫
    tool_timeout_override: Dict[str, float] = field(default_factory=dict)
    
    # 工具依賴關係
    tool_dependencies: Dict[str, list] = field(default_factory=dict)
    
    # 警告閾值
    alert_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "response_time": 10.0,
        "error_rate": 0.1,
        "cache_hit_rate": 0.5,
        "memory_search_time": 5.0
    })

class OptimizationConfigManager:
    """優化配置管理器"""
    
    def __init__(self, config_path: str = "config/optimization_config.json"):
        """初始化配置管理器
        
        Args:
            config_path: 配置檔案路徑
        """
        self.config_path = Path(config_path)
        self.logger = logging.getLogger(__name__)
        self._config_data: Optional[Dict[str, Any]] = None
        self._settings: Optional[OptimizationSettings] = None
        self._environment = self._detect_environment()
        
        # 載入配置
        self._load_config()
    
    def _detect_environment(self) -> str:
        """自動偵測運行環境"""
        # 檢查環境變數
        env = os.getenv('DISCORD_BOT_ENV', '').lower()
        if env in ['production', 'prod']:
            return 'production'
        elif env in ['development', 'dev']:
            return 'development'
        elif env in ['testing', 'test']:
            return 'testing'
        
        # 根據其他指標判斷
        if os.getenv('DEBUG') == 'True':
            return 'development'
        
        # 預設為開發環境
        return 'development'
    
    def _load_config(self) -> None:
        """載入配置檔案"""
        try:
            if not self.config_path.exists():
                self.logger.warning(f"配置檔案不存在: {self.config_path}，使用預設配置")
                self._create_default_config()
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config_data = json.load(f)
            
            self.logger.info(f"成功載入配置檔案: {self.config_path}")
            self._parse_settings()
            
        except json.JSONDecodeError as e:
            func.report_error(e, "optimization config JSON decode error")
            self._create_default_config()
        except Exception as e:
            func.report_error(e, "optimization config load error")
            self._create_default_config()
    
    def _create_default_config(self) -> None:
        """創建預設配置"""
        self.logger.info("使用預設優化配置")
        self._settings = OptimizationSettings()
    
    def _parse_settings(self) -> None:
        """解析配置設定"""
        if not self._config_data:
            self._create_default_config()
            return
        
        try:
            # 基礎設定
            optimization = self._config_data.get('optimization_settings', {})
            if not optimization.get('enabled', True):
                self.logger.warning("優化功能已在配置中停用")
                self._settings = OptimizationSettings()
                self._settings.enable_gemini_cache = False
                self._settings.enable_processing_cache = False
                self._settings.enable_memory_cache = False
                self._settings.enable_parallel_tools = False
                self._settings.enable_performance_monitoring = False
                return
            
            # 環境特定配置
            env_config = self._config_data.get('environment_specific', {}).get(self._environment, {})
            
            # 解析各模組配置
            gemini_config = self._config_data.get('gemini_cache', {})
            processing_config = self._config_data.get('processing_cache', {})
            memory_config = self._config_data.get('memory_cache', {})
            parallel_config = self._config_data.get('parallel_tools', {})
            monitoring_config = self._config_data.get('performance_monitoring', {})
            cleanup_config = self._config_data.get('auto_cleanup', {})
            fallback_config = self._config_data.get('fallback_settings', {})
            
            # 構建設定物件
            self._settings = OptimizationSettings(
                # Gemini 快取
                enable_gemini_cache=gemini_config.get('enabled', True),
                gemini_cache_ttl=env_config.get('gemini_cache_ttl', gemini_config.get('ttl', '3600s')),
                gemini_max_cache_count=gemini_config.get('max_cache_count', 50),
                
                # 處理快取
                enable_processing_cache=processing_config.get('enabled', True),
                processing_cache_ttl=env_config.get('processing_cache_ttl', processing_config.get('ttl', 300)),
                processing_max_cache_size=processing_config.get('max_cache_size', 1000),
                
                # 記憶快取
                enable_memory_cache=memory_config.get('enabled', True),
                memory_cache_ttl=memory_config.get('ttl', 1800),
                memory_max_search_results=memory_config.get('max_search_results', 100),
                
                # 並行工具
                enable_parallel_tools=parallel_config.get('enabled', True),
                max_parallel_workers=env_config.get('max_parallel_workers', parallel_config.get('max_workers', 4)),
                tool_default_timeout=parallel_config.get('default_timeout', 30.0),
                tool_timeout_override=parallel_config.get('tool_timeout_override', {}),
                tool_dependencies=parallel_config.get('dependencies', {}),
                
                # 性能監控
                enable_performance_monitoring=monitoring_config.get('enabled', True),
                performance_max_history=env_config.get('performance_history', monitoring_config.get('max_history', 1000)),
                alert_thresholds=monitoring_config.get('alert_thresholds', {}),
                
                # 自動清理
                enable_auto_cleanup=cleanup_config.get('enabled', True),
                auto_cleanup_interval=cleanup_config.get('interval', 3600),
                
                # 降級設定
                enable_graceful_degradation=fallback_config.get('enable_graceful_degradation', True),
                fallback_timeout=fallback_config.get('fallback_timeout', 5.0),
                max_retry_attempts=fallback_config.get('max_retry_attempts', 3)
            )
            
            self.logger.info(f"配置解析完成，環境: {self._environment}")
            
        except Exception as e:
            func.report_error(e, "optimization config parse error")
            self._create_default_config()
    
    def get_settings(self) -> OptimizationSettings:
        """獲取優化設定"""
        if self._settings is None:
            self._create_default_config()
        return self._settings
    
    def reload_config(self) -> bool:
        """重新載入配置"""
        try:
            self._load_config()
            self.logger.info("配置重新載入成功")
            return True
        except Exception as e:
            func.report_error(e, "optimization config reload error")
            return False
    
    def get_environment(self) -> str:
        """獲取當前環境"""
        return self._environment
    
    def is_optimization_enabled(self) -> bool:
        """檢查優化功能是否啟用"""
        if not self._config_data:
            return True  # 預設啟用
        
        optimization = self._config_data.get('optimization_settings', {})
        return optimization.get('enabled', True)
    
    def get_tool_timeout(self, tool_name: str) -> float:
        """獲取特定工具的超時時間"""
        settings = self.get_settings()
        return settings.tool_timeout_override.get(tool_name, settings.tool_default_timeout)
    
    def get_tool_dependencies(self, tool_name: str) -> list:
        """獲取特定工具的依賴關係"""
        settings = self.get_settings()
        return settings.tool_dependencies.get(tool_name, [])
    
    def is_alert_threshold_exceeded(self, metric: str, value: float) -> bool:
        """檢查是否超過警告閾值"""
        settings = self.get_settings()
        threshold = settings.alert_thresholds.get(metric)
        if threshold is None:
            return False
        
        # 對於快取命中率，低於閾值才是問題
        if metric == 'cache_hit_rate':
            return value < threshold
        
        # 對於其他指標，高於閾值才是問題
        return value > threshold
    
    def get_gemini_cache_config(self) -> Dict[str, Any]:
        """獲取Gemini快取配置"""
        if not self._config_data:
            return {'enabled': True, 'max_cache_count': 30}
        return self._config_data.get('gemini_cache', {})
    
    def get_processing_cache_config(self) -> Dict[str, Any]:
        """獲取處理快取配置"""
        if not self._config_data:
            return {'enabled': True, 'max_cache_size': 500}
        return self._config_data.get('processing_cache', {})
    
    def get_memory_cache_config(self) -> Dict[str, Any]:
        """獲取記憶快取配置"""
        if not self._config_data:
            return {'enabled': True, 'max_search_results': 50}
        return self._config_data.get('memory_cache', {})
    
    def get_parallel_tools_config(self) -> Dict[str, Any]:
        """獲取並行工具配置"""
        if not self._config_data:
            return {'enabled': True, 'max_workers': 4}
        return self._config_data.get('parallel_tools', {})
    
    def get_auto_cleanup_config(self) -> Dict[str, Any]:
        """獲取自動清理配置"""
        if not self._config_data:
            return {'enabled': True, 'interval': 1800}
        return self._config_data.get('auto_cleanup', {})
    
    def get_gpu_memory_config(self) -> Dict[str, Any]:
        """獲取GPU記憶體管理配置"""
        if not self._config_data:
            return {
                'enabled': True,
                'memory_threshold': 75.0,
                'cleanup_threshold': 70.0,
                'force_cleanup_threshold': 85.0,
                'auto_cleanup_interval': 300
            }
        return self._config_data.get('gpu_memory_management', {
            'enabled': True,
            'memory_threshold': 75.0,
            'cleanup_threshold': 70.0,
            'force_cleanup_threshold': 85.0,
            'auto_cleanup_interval': 300
        })
    
    def get_environment_config(self, environment: str = None) -> Dict[str, Any]:
        """獲取環境特定配置
        
        Args:
            environment: 環境名稱 (production, development, testing)
            
        Returns:
            環境配置
        """
        if not self._config_data:
            return {}
        
        env_configs = self._config_data.get('environment_specific', {})
        
        if environment is None:
            environment = self._environment
        
        return env_configs.get(environment, env_configs.get('development', {}))
    
    def get_cache_size_limits(self, environment: str = None) -> Dict[str, Any]:
        """獲取快取大小限制配置
        
        Args:
            environment: 環境名稱
            
        Returns:
            快取大小限制配置
        """
        env_config = self.get_environment_config(environment)
        gemini_config = self.get_gemini_cache_config()
        processing_config = self.get_processing_cache_config()
        memory_config = self.get_memory_cache_config()
        
        return {
            'gemini_cache_max_count': env_config.get('gemini_cache_max_count', gemini_config.get('max_cache_count', 30)),
            'processing_cache_max_size': env_config.get('processing_cache_max_size', processing_config.get('max_cache_size', 500)),
            'memory_cache_max_results': memory_config.get('max_search_results', 50),
            'memory_results_retention': memory_config.get('max_results_retention', 100),
            'gpu_memory_threshold': env_config.get('gpu_memory_threshold', 75.0)
        }

    def export_config_summary(self) -> Dict[str, Any]:
        """匯出配置摘要"""
        settings = self.get_settings()
        
        return {
            "environment": self._environment,
            "optimization_enabled": self.is_optimization_enabled(),
            "modules": {
                "gemini_cache": settings.enable_gemini_cache,
                "processing_cache": settings.enable_processing_cache,
                "memory_cache": settings.enable_memory_cache,
                "parallel_tools": settings.enable_parallel_tools,
                "performance_monitoring": settings.enable_performance_monitoring
            },
            "performance_settings": {
                "max_parallel_workers": settings.max_parallel_workers,
                "gemini_cache_ttl": settings.gemini_cache_ttl,
                "processing_cache_ttl": settings.processing_cache_ttl,
                "memory_cache_ttl": settings.memory_cache_ttl
            },
            "cache_limits": self.get_cache_size_limits(),
            "gpu_memory_config": self.get_gpu_memory_config(),
            "alert_thresholds": settings.alert_thresholds,
            "config_path": str(self.config_path),
            "last_loaded": self._config_data.get('timestamp') if self._config_data else None
        }

# 全域配置管理器實例
_config_manager: Optional[OptimizationConfigManager] = None

def get_config_manager() -> OptimizationConfigManager:
    """獲取配置管理器實例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = OptimizationConfigManager()
    return _config_manager

def get_optimization_settings() -> OptimizationSettings:
    """便捷函數：獲取優化設定"""
    return get_config_manager().get_settings()

def reload_optimization_config() -> bool:
    """便捷函數：重新載入配置"""
    return get_config_manager().reload_config()

def is_optimization_enabled() -> bool:
    """便捷函數：檢查優化是否啟用"""
    return get_config_manager().is_optimization_enabled()