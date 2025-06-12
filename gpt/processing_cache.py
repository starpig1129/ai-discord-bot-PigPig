"""
處理結果快取模組

用於優化 choose_act.py 和 sendmessage.py 之間的雙層架構性能問題。
實現第一次處理結果的快取，避免重複計算。
"""

import time
import hashlib
import logging
import asyncio
from typing import Any, Dict, Optional, Tuple, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ProcessingCache:
    """處理結果快取管理器"""
    
    def __init__(self, default_ttl: int = 300, max_cache_size: int = 1000):
        """初始化處理快取
        
        Args:
            default_ttl: 預設TTL（秒），預設5分鐘
            max_cache_size: 最大快取大小
        """
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.default_ttl = default_ttl
        self.max_cache_size = max_cache_size
        self.logger = logging.getLogger(__name__)
        self.hit_count = 0
        self.miss_count = 0
        
        # 快取存取時間追蹤（用於LRU清理）
        self.access_times: Dict[str, float] = {}
        self.cleanup_threshold = max(int(max_cache_size * 0.8), 1)  # 80% 時開始清理
        
    def _generate_cache_key(self,
                           user_input: str,
                           user_id: str,
                           channel_id: str,
                           additional_context: str = "") -> str:
        """生成快取鍵值
        
        Args:
            user_input: 用戶輸入
            user_id: 用戶ID
            channel_id: 頻道ID
            additional_context: 額外上下文
            
        Returns:
            str: 快取鍵值
        """
        # 優化鍵值生成策略 - 移除時間分組以提高命中率
        # 對用戶輸入進行標準化處理
        normalized_input = user_input.strip().lower()
        
        # 結合多個因素生成唯一鍵值
        key_components = [
            normalized_input,
            user_id,
            channel_id,
            additional_context
        ]
        
        key_string = "|".join(key_components)
        return hashlib.sha256(key_string.encode('utf-8')).hexdigest()[:32]
    
    def get_cached_result(self, 
                         user_input: str,
                         user_id: str,
                         channel_id: str,
                         additional_context: str = "") -> Optional[Any]:
        """獲取快取的處理結果
        
        Args:
            user_input: 用戶輸入
            user_id: 用戶ID
            channel_id: 頻道ID
            additional_context: 額外上下文
            
        Returns:
            快取的結果或 None
        """
        cache_key = self._generate_cache_key(user_input, user_id, channel_id, additional_context)
        
        if cache_key in self.cache:
            result, timestamp = self.cache[cache_key]
            
            # 檢查是否過期
            if time.time() - timestamp < self.default_ttl:
                self.hit_count += 1
                # 更新存取時間
                self.access_times[cache_key] = time.time()
                self.logger.debug(f"快取命中: {cache_key[:16]}...")
                return result
            else:
                # 清理過期快取
                self._remove_cache_entry(cache_key)
                self.logger.debug(f"快取過期已清理: {cache_key[:16]}...")
        
        self.miss_count += 1
        self.logger.debug(f"快取未命中: {cache_key[:16]}...")
        return None
    
    def cache_result(self, 
                    user_input: str,
                    user_id: str,
                    channel_id: str,
                    result: Any,
                    additional_context: str = "",
                    ttl: Optional[int] = None) -> str:
        """快取處理結果
        
        Args:
            user_input: 用戶輸入
            user_id: 用戶ID
            channel_id: 頻道ID
            result: 要快取的結果
            additional_context: 額外上下文
            ttl: 自定義TTL（秒）
            
        Returns:
            str: 快取鍵值
        """
        # 檢查快取大小限制，必要時清理
        if len(self.cache) >= self.cleanup_threshold:
            self._cleanup_least_used_cache()
        
        cache_key = self._generate_cache_key(user_input, user_id, channel_id, additional_context)
        
        # 使用自定義TTL或預設TTL
        actual_ttl = ttl if ttl is not None else self.default_ttl
        
        # 儲存結果和時間戳
        current_time = time.time()
        self.cache[cache_key] = (result, current_time)
        self.access_times[cache_key] = current_time
        
        self.logger.debug(f"結果已快取: {cache_key[:16]}..., TTL: {actual_ttl}s, 當前快取大小: {len(self.cache)}")
        return cache_key
    
    def invalidate_cache(self, cache_key: str) -> bool:
        """手動無效化特定快取
        
        Args:
            cache_key: 快取鍵值
            
        Returns:
            bool: 是否成功刪除
        """
        if cache_key in self.cache:
            self._remove_cache_entry(cache_key)
            self.logger.debug(f"手動無效化快取: {cache_key[:16]}...")
            return True
        return False
    
    def cleanup_expired_cache(self) -> int:
        """清理所有過期的快取
        
        Returns:
            int: 清理的快取數量
        """
        current_time = time.time()
        expired_keys = []
        
        for cache_key, (result, timestamp) in self.cache.items():
            if current_time - timestamp >= self.default_ttl:
                expired_keys.append(cache_key)
        
        for key in expired_keys:
            self._remove_cache_entry(key)
        
        if expired_keys:
            self.logger.info(f"清理了 {len(expired_keys)} 個過期快取")
        
        return len(expired_keys)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """獲取快取統計資訊
        
        Returns:
            dict: 統計資訊
        """
        total_requests = self.hit_count + self.miss_count
        hit_ratio = (self.hit_count / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'cache_size': len(self.cache),
            'hit_count': self.hit_count,
            'miss_count': self.miss_count,
            'hit_ratio': f"{hit_ratio:.2f}%",
            'default_ttl': self.default_ttl,
            'last_cleanup': datetime.now().isoformat()
        }
    
    def clear_all_cache(self) -> int:
        """清空所有快取
        
        Returns:
            int: 清理的快取數量
        """
        cache_count = len(self.cache)
        self.cache.clear()
        self.access_times.clear()
        self.hit_count = 0
        self.miss_count = 0
        
        self.logger.info(f"清空了所有快取，共 {cache_count} 個項目")
        return cache_count
    
    def _remove_cache_entry(self, cache_key: str) -> None:
        """移除快取項目及其存取時間記錄
        
        Args:
            cache_key: 快取鍵值
        """
        if cache_key in self.cache:
            del self.cache[cache_key]
        if cache_key in self.access_times:
            del self.access_times[cache_key]
    
    def _cleanup_least_used_cache(self) -> int:
        """清理最少使用的快取（LRU策略）
        
        Returns:
            int: 清理的快取數量
        """
        cleaned_count = 0
        
        try:
            # 如果快取數量未超過限制，不執行清理
            if len(self.cache) < self.cleanup_threshold:
                return 0
            
            # 計算需要清理的數量（清理到最大限制的60%）
            target_count = max(int(self.max_cache_size * 0.6), 1)
            cleanup_count = len(self.cache) - target_count
            
            if cleanup_count <= 0:
                return 0
            
            # 按存取時間排序，清理最舊的快取
            cache_items = []
            for cache_key in self.cache.keys():
                access_time = self.access_times.get(cache_key, 0)
                cache_items.append((access_time, cache_key))
            
            # 排序（最舊的在前）
            cache_items.sort(key=lambda x: x[0])
            
            # 清理最舊的快取
            for i in range(min(cleanup_count, len(cache_items))):
                _, cache_key = cache_items[i]
                self._remove_cache_entry(cache_key)
                cleaned_count += 1
            
            self.logger.info(f"主動清理了 {cleaned_count} 個最少使用的處理快取，當前快取數量: {len(self.cache)}")
            
        except Exception as e:
            self.logger.error(f"清理最少使用的處理快取失敗: {str(e)}")
        
        return cleaned_count
    
    def get_cache_size_info(self) -> Dict[str, Any]:
        """獲取快取大小資訊
        
        Returns:
            Dict[str, Any]: 快取大小統計
        """
        return {
            'current_count': len(self.cache),
            'max_count': self.max_cache_size,
            'cleanup_threshold': self.cleanup_threshold,
            'usage_ratio': len(self.cache) / self.max_cache_size if self.max_cache_size > 0 else 0,
            'needs_cleanup': len(self.cache) >= self.cleanup_threshold
        }

class MemorySearchCache:
    """記憶搜索結果快取"""
    
    def __init__(self, default_ttl: int = 1800):  # 預設30分鐘
        """初始化記憶搜索快取
        
        Args:
            default_ttl: 預設TTL（秒）
        """
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.default_ttl = default_ttl
        self.logger = logging.getLogger(__name__)
        
    def _generate_search_key(self, 
                           query: str,
                           user_id: str,
                           search_type: str = "semantic") -> str:
        """生成搜索快取鍵值
        
        Args:
            query: 搜索查詢
            user_id: 用戶ID
            search_type: 搜索類型
            
        Returns:
            str: 快取鍵值
        """
        key_string = f"{query}|{user_id}|{search_type}"
        return hashlib.sha256(key_string.encode('utf-8')).hexdigest()[:32]
    
    def get_search_result(self, 
                         query: str,
                         user_id: str,
                         search_type: str = "semantic") -> Optional[Any]:
        """獲取快取的搜索結果
        
        Args:
            query: 搜索查詢
            user_id: 用戶ID
            search_type: 搜索類型
            
        Returns:
            快取的搜索結果或 None
        """
        cache_key = self._generate_search_key(query, user_id, search_type)
        
        if cache_key in self.cache:
            result, timestamp = self.cache[cache_key]
            
            if time.time() - timestamp < self.default_ttl:
                self.logger.debug(f"記憶搜索快取命中: {cache_key[:16]}...")
                return result
            else:
                del self.cache[cache_key]
                
        return None
    
    def cache_search_result(self, 
                           query: str,
                           user_id: str,
                           result: Any,
                           search_type: str = "semantic") -> str:
        """快取搜索結果
        
        Args:
            query: 搜索查詢
            user_id: 用戶ID
            result: 搜索結果
            search_type: 搜索類型
            
        Returns:
            str: 快取鍵值
        """
        cache_key = self._generate_search_key(query, user_id, search_type)
        self.cache[cache_key] = (result, time.time())
        
        self.logger.debug(f"記憶搜索結果已快取: {cache_key[:16]}...")
        return cache_key

# 全域快取實例
processing_cache = ProcessingCache(default_ttl=300, max_cache_size=1000)
memory_search_cache = MemorySearchCache(default_ttl=1800)

# 便捷函數
def get_processing_result(user_input: str, user_id: str, channel_id: str, context: str = "") -> Optional[Any]:
    """便捷函數：獲取處理結果快取"""
    return processing_cache.get_cached_result(user_input, user_id, channel_id, context)

def cache_processing_result(user_input: str, user_id: str, channel_id: str, result: Any, context: str = "") -> str:
    """便捷函數：快取處理結果"""
    return processing_cache.cache_result(user_input, user_id, channel_id, result, context)

def get_memory_search_result(query: str, user_id: str, search_type: str = "semantic") -> Optional[Any]:
    """便捷函數：獲取記憶搜索結果快取"""
    return memory_search_cache.get_search_result(query, user_id, search_type)

def cache_memory_search_result(query: str, user_id: str, result: Any, search_type: str = "semantic") -> str:
    """便捷函數：快取記憶搜索結果"""
    return memory_search_cache.cache_search_result(query, user_id, result, search_type)

def cleanup_all_caches() -> Dict[str, int]:
    """便捷函數：清理所有快取"""
    processing_cleaned = processing_cache.cleanup_expired_cache()
    
    return {
        'processing_cache_cleaned': processing_cleaned,
        'memory_cache_size': len(memory_search_cache.cache)
    }

def get_all_cache_stats() -> Dict[str, Any]:
    """便捷函數：獲取所有快取統計"""
    return {
        'processing_cache': processing_cache.get_cache_stats(),
        'memory_search_cache': {
            'cache_size': len(memory_search_cache.cache),
            'default_ttl': memory_search_cache.default_ttl
        }
    }