import yaml
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

class PromptLoader:
    """YAML 提示配置載入器"""
    
    def __init__(self, config_path: str = "./systemPrompt.yaml"):
        """
        初始化載入器
        
        Args:
            config_path: YAML 配置檔案路徑
        """
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)
        self._cached_config: Optional[Dict[str, Any]] = None
        self._last_loaded: Optional[datetime] = None
        
    def load_yaml_config(self) -> Dict[str, Any]:
        """
        載入 YAML 配置檔案
        
        Returns:
            解析後的配置字典
            
        Raises:
            FileNotFoundError: 配置檔案不存在
            yaml.YAMLError: YAML 解析錯誤
        """
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                
            if config is None:
                raise ValueError("Empty or invalid YAML configuration")
                
            self._cached_config = config
            self._last_loaded = datetime.now()
            
            self.logger.debug(f"Successfully loaded configuration from {self.config_path}")
            return config
            
        except yaml.YAMLError as e:
            self.logger.error(f"YAML parsing error in {self.config_path}: {e}")
            raise
        except Exception as e:
            func.report_error(e, f"loading configuration from {self.config_path}")
            raise
    
    def reload_if_changed(self) -> bool:
        """
        檢查檔案是否變更，如有變更則重新載入
        
        Returns:
            bool: 是否重新載入了配置
        """
        try:
            if not os.path.exists(self.config_path):
                return False
                
            current_mtime = datetime.fromtimestamp(os.path.getmtime(self.config_path))
            
            if self._last_loaded is None or current_mtime > self._last_loaded:
                self.load_yaml_config()
                self.logger.info(f"Configuration reloaded due to file changes: {self.config_path}")
                return True
                
            return False
            
        except Exception as e:
            func.report_error(e, "checking for file changes")
            return False
    
    def get_last_modified(self) -> Optional[datetime]:
        """
        獲取配置檔案的最後修改時間
        
        Returns:
            最後修改時間，如果檔案不存在則返回 None
        """
        try:
            if os.path.exists(self.config_path):
                return datetime.fromtimestamp(os.path.getmtime(self.config_path))
            return None
        except Exception as e:
            func.report_error(e, "getting file modification time")
            return None
    
    def get_cached_config(self) -> Optional[Dict[str, Any]]:
        """
        獲取快取的配置（不重新載入檔案）
        
        Returns:
            快取的配置字典，如果未載入則返回 None
        """
        return self._cached_config
    
    def is_config_loaded(self) -> bool:
        """
        檢查配置是否已載入
        
        Returns:
            bool: 配置是否已載入
        """
        return self._cached_config is not None
    
    def get_config_section(self, section_name: str) -> Optional[Dict[str, Any]]:
        """
        獲取配置的特定區段
        
        Args:
            section_name: 區段名稱
            
        Returns:
            指定區段的配置，如果不存在則返回 None
        """
        if self._cached_config is None:
            self.load_yaml_config()
            
        return self._cached_config.get(section_name) if self._cached_config else None
    
    def validate_config_structure(self, config: Dict[str, Any]) -> bool:
        """
        驗證配置結構的基本完整性
        
        Args:
            config: 要驗證的配置字典
            
        Returns:
            bool: 配置結構是否有效
        """
        required_sections = ['metadata', 'base', 'composition']
        
        try:
            # 檢查必要的頂層區段
            for section in required_sections:
                if section not in config:
                    self.logger.error(f"Missing required section: {section}")
                    return False
            
            # 檢查 composition 區段的必要欄位
            composition = config.get('composition', {})
            if 'default_modules' not in composition:
                self.logger.error("Missing 'default_modules' in composition section")
                return False
            
            # 檢查預設模組是否都存在
            default_modules = composition['default_modules']
            for module in default_modules:
                if module not in config:
                    self.logger.warning(f"Default module '{module}' not found in configuration")
            
            return True
            
        except Exception as e:
            func.report_error(e, "configuration validation")
            return False