import threading
import logging
from typing import Dict, Any, Optional, Set
from datetime import datetime, timedelta

class PromptCache:
    """智慧快取系統"""
    
    def __init__(self):
        """初始化快取系統"""
        self.cache_storage: Dict[str, Any] = {}
        self.ttl_storage: Dict[str, datetime] = {}
        self.precompiled_cache: Dict[str, str] = {}
        self.access_count: Dict[str, int] = {}
        self._lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        
    def get(self, key: str) -> Optional[Any]:
        """
        取得快取項目
        
        Args:
            key: 快取鍵值
            
        Returns:
            快取的值，如果不存在或已過期則返回 None
        """
        with self._lock:
            if key not in self.cache_storage:
                return None
            
            if self.is_expired(key):
                self.invalidate(key)
                return None
            
            # 記錄存取次數
            self.access_count[key] = self.access_count.get(key, 0) + 1
            
            return self.cache_storage[key]
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """
        設定快取項目
        
        Args:
            key: 快取鍵值
            value: 要快取的值
            ttl: 生存時間（秒）
        """
        with self._lock:
            self.cache_storage[key] = value
            self.ttl_storage[key] = datetime.now() + timedelta(seconds=ttl)
            self.access_count[key] = 0
            
            self.logger.debug(f"Cached item: {key} (TTL: {ttl}s)")
    
    def invalidate(self, key: str) -> None:
        """
        清除指定快取項目
        
        Args:
            key: 要清除的快取鍵值
        """
        with self._lock:
            self.cache_storage.pop(key, None)
            self.ttl_storage.pop(key, None)
            self.access_count.pop(key, None)
            self.precompiled_cache.pop(key, None)
            
            self.logger.debug(f"Invalidated cache item: {key}")
    
    def clear_all(self) -> None:
        """清除所有快取"""
        with self._lock:
            cleared_count = len(self.cache_storage)
            self.cache_storage.clear()
            self.ttl_storage.clear()
            self.precompiled_cache.clear()
            self.access_count.clear()
            
            self.logger.info(f"Cleared all cache ({cleared_count} items)")
    
    def is_expired(self, key: str) -> bool:
        """
        檢查快取是否過期
        
        Args:
            key: 快取鍵值
            
        Returns:
            bool: 是否已過期
        """
        if key not in self.ttl_storage:
            return True
        return datetime.now() > self.ttl_storage[key]
    
    def precompile_templates(self, config: dict) -> None:
        """
        預編譯提示模板
        
        Args:
            config: 配置字典
        """
        with self._lock:
            self.precompiled_cache.clear()
            
            try:
                # 預編譯常用組合
                default_modules = config.get('composition', {}).get('default_modules', [])
                module_order = config.get('composition', {}).get('module_order', default_modules)
                
                # 預編譯不同長度的模組組合
                for i in range(1, len(default_modules) + 1):
                    module_combo = [mod for mod in module_order if mod in default_modules[:i]]
                    combo_key = '_'.join(module_combo)
                    
                    # 建構組合的部分提示（由 PromptBuilder 實際處理）
                    self.precompiled_cache[f"combo_{combo_key}"] = combo_key
                
                # 預編譯單個模組
                for module in default_modules:
                    if module in config:
                        self.precompiled_cache[f"module_{module}"] = module
                
                self.logger.info(f"Precompiled {len(self.precompiled_cache)} template combinations")
                
            except Exception as e:
                self.logger.error(f"Failed to precompile templates: {e}")
    
    def get_precompiled(self, key: str) -> Optional[str]:
        """
        取得預編譯的模板
        
        Args:
            key: 預編譯模板的鍵值
            
        Returns:
            預編譯的模板，如果不存在則返回 None
        """
        return self.precompiled_cache.get(key)
    
    def cleanup_expired(self) -> int:
        """
        清理過期的快取項目
        
        Returns:
            清理的項目數量
        """
        with self._lock:
            expired_keys = []
            
            for key in list(self.cache_storage.keys()):
                if self.is_expired(key):
                    expired_keys.append(key)
            
            for key in expired_keys:
                self.invalidate(key)
            
            if expired_keys:
                self.logger.debug(f"Cleaned up {len(expired_keys)} expired cache items")
            
            return len(expired_keys)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        獲取快取統計資訊
        
        Returns:
            包含快取統計資訊的字典
        """
        with self._lock:
            total_items = len(self.cache_storage)
            expired_items = sum(1 for key in self.cache_storage.keys() if self.is_expired(key))
            precompiled_items = len(self.precompiled_cache)
            
            # 計算總存取次數
            total_access = sum(self.access_count.values())
            
            # 找出最常存取的項目
            most_accessed = None
            if self.access_count:
                most_accessed = max(self.access_count.items(), key=lambda x: x[1])
            
            return {
                'total_items': total_items,
                'expired_items': expired_items,
                'active_items': total_items - expired_items,
                'precompiled_items': precompiled_items,
                'total_access_count': total_access,
                'most_accessed': most_accessed
            }
    
    def get_cache_keys(self, prefix: str = None) -> Set[str]:
        """
        獲取快取鍵值列表
        
        Args:
            prefix: 可選的前綴過濾
            
        Returns:
            快取鍵值集合
        """
        with self._lock:
            if prefix:
                return {key for key in self.cache_storage.keys() if key.startswith(prefix)}
            return set(self.cache_storage.keys())
    
    def extend_ttl(self, key: str, additional_seconds: int) -> bool:
        """
        延長快取項目的生存時間
        
        Args:
            key: 快取鍵值
            additional_seconds: 要延長的秒數
            
        Returns:
            bool: 是否成功延長（項目存在且未過期）
        """
        with self._lock:
            if key in self.ttl_storage and not self.is_expired(key):
                self.ttl_storage[key] += timedelta(seconds=additional_seconds)
                self.logger.debug(f"Extended TTL for {key} by {additional_seconds} seconds")
                return True
            return False