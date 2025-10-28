"""
Gemini API 快取工具模組

提供便捷的快取管理功能，支援 Discord 機器人的性能優化。
"""

import logging
import time
import asyncio
from google.genai import types
from google.genai.types import Tool
from typing import Optional, Dict, Any, List
from google import genai
from function import func

logger = logging.getLogger(__name__)

class GeminiCacheManager:
    """Gemini API 顯式快取管理器
    
    基於官方 Gemini API 文檔實現的快取系統，用於提升性能並降低 API 調用成本。
    支援快取大小限制和主動清理機制。
    """
    
    def __init__(self, client: genai.Client, max_cache_count: int = 50):
        self.client = client
        self.active_caches: Dict[str, Any] = {}
        self.cache_metadata: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
        
        # 快取大小限制和清理設定
        self.max_cache_count = max_cache_count
        self.cache_access_times: Dict[str, float] = {}  # 快取存取時間記錄
        self.cleanup_threshold = max(int(max_cache_count * 0.8), 1)  # 80% 時開始清理

    def create_and_register_cache(self,
                                  cache_key: str,
                                  model: str,
                                  system_instruction: str,
                                  contents: List[Any],
                                  ttl: str,
                                  display_name: str,
                                  tools: Optional[List[Tool]] = None) -> Optional[Any]:
        """
        # <<< 新增：一個更明確的函數，用於創建遠端快取並在本地註冊。
        """
        try:
            if len(self.active_caches) >= self.cleanup_threshold:
                asyncio.create_task(self._cleanup_least_used_caches())

            self.logger.info(f"本地快取未命中。正在創建新的遠端快取: '{display_name}'...")
            config = types.CreateCachedContentConfig(
                system_instruction=system_instruction,
                contents=contents,
                ttl=ttl,
                display_name=display_name,
                tools=tools
            )
            cache = self.client.caches.create(
                model=model,
                config=config
            )
            
            self.active_caches[cache_key] = cache
            self.cache_metadata[cache_key] = {
                'cache_name': cache.name,
                'created_time': time.time(),
                'ttl': ttl,
                'display_name': display_name,
                'system_instruction': system_instruction,
                'model': model
            }
            self.cache_access_times[cache_key] = time.time()
            
            self.logger.info(f"成功創建新快取: {cache.name} (本地key: {cache_key})")
            return cache
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Gemini cache creation"))
            return None

    async def get_cache_by_key(self, cache_key: str) -> Optional[Any]:
        """根據（由內容生成的）唯一鍵值獲取快取"""
        if cache_key in self.active_caches:
            cache = None
            try:
                cache = self.active_caches[cache_key]
                # 驗證遠端快取是否仍然存在
                await asyncio.to_thread(self.client.caches.get, name=cache.name)
                self.logger.info(f"本地快取命中: {cache_key} -> {cache.name}")
                self.cache_access_times[cache_key] = time.time()
                return cache
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"Gemini cache access for cache"))
                self._cleanup_cache_record(cache_key)
        return None

    def _cleanup_cache_record(self, cache_key: str):
        """清理本地快取記錄"""
        if cache_key in self.active_caches: del self.active_caches[cache_key]
        if cache_key in self.cache_metadata: del self.cache_metadata[cache_key]
        if cache_key in self.cache_access_times: del self.cache_access_times[cache_key]

    async def delete_cache(self, cache_key: str) -> bool:
        """根據本地 key 刪除遠端快取並清理本地記錄
        
        Args:
            cache_key (str): 要刪除的快取的本地鍵
            
        Returns:
            bool: 如果成功啟動刪除過程則返回 True
        """
        if cache_key in self.active_caches:
            cache = self.active_caches[cache_key]
            try:
                self.logger.info(f"正在刪除遠端快取: {cache.name} (本地 key: {cache_key})")
                await asyncio.to_thread(self.client.caches.delete, name=cache.name)
                self.logger.info(f"成功刪除遠端快取: {cache.name}")
            except Exception as e:
                # 如果遠端快取已不存在（例如，已過期或手動刪除），也視為成功
                await func.report_error(e, f"Gemini cache deletion for {cache.name}")
            finally:
                # 無論遠端刪除是否成功，都清理本地記錄
                self._cleanup_cache_record(cache_key)
            return True
        self.logger.debug(f"嘗試刪除一個不存在的本地快取 key: {cache_key}")
        return False
        
    async def _cleanup_least_used_caches(self) -> int:
        """清理最少使用的快取
        
        Returns:
            int: 清理的快取數量
        """
        cleaned_count = 0
        
        try:
            # 如果快取數量未超過限制，不執行清理
            if len(self.active_caches) < self.cleanup_threshold:
                return 0
            
            # 計算需要清理的數量（清理到最大限制的60%）
            target_count = max(int(self.max_cache_count * 0.6), 1)
            cleanup_count = len(self.active_caches) - target_count
            
            if cleanup_count <= 0:
                return 0
            
            # 按存取時間排序，清理最舊的快取
            cache_items = []
            for cache_key in self.active_caches.keys():
                access_time = self.cache_access_times.get(cache_key, 0)
                cache_items.append((access_time, cache_key))
            
            # 排序（最舊的在前）
            cache_items.sort(key=lambda x: x[0])
            
            # 清理最舊的快取
            for i in range(min(cleanup_count, len(cache_items))):
                _, cache_key = cache_items[i]
                if await self.delete_cache(cache_key):
                    cleaned_count += 1
            
            self.logger.info(f"主動清理了 {cleaned_count} 個最少使用的快取，當前快取數量: {len(self.active_caches)}")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "least used Gemini cache cleanup"))
        
        return cleaned_count
    
    async def force_cleanup_all_caches(self) -> int:
        """強制清理所有快取
        
        Returns:
            int: 清理的快取數量
        """
        cleaned_count = 0
        cache_keys = list(self.active_caches.keys())
        
        for cache_key in cache_keys:
            if await self.delete_cache(cache_key):
                cleaned_count += 1
        
        self.logger.warning(f"強制清理了所有快取，共 {cleaned_count} 個")
        return cleaned_count
    
    def get_cache_size_info(self) -> Dict[str, Any]:
        """獲取快取大小資訊
        
        Returns:
            Dict[str, Any]: 快取大小統計
        """
        return {
            'current_count': len(self.active_caches),
            'max_count': self.max_cache_count,
            'cleanup_threshold': self.cleanup_threshold,
            'usage_ratio': len(self.active_caches) / self.max_cache_count if self.max_cache_count > 0 else 0,
            'needs_cleanup': len(self.active_caches) >= self.cleanup_threshold
        }