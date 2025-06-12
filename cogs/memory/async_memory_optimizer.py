"""
異步記憶搜索優化模組

用於提前並行執行記憶搜索，減少主處理流程的阻塞時間。
實現記憶系統的預處理和上下文預構建功能。
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from cogs.memory.memory_manager import MemoryManager, SearchQuery, SearchType
from cogs.memory.exceptions import MemorySystemError, SearchError
from gpt.processing_cache import memory_search_cache

logger = logging.getLogger(__name__)

@dataclass
class MemorySearchTask:
    """記憶搜索任務"""
    query: str
    user_id: str
    search_type: SearchType = SearchType.SEMANTIC
    limit: int = 10
    threshold: float = 0.7
    include_context: bool = True
    task_id: str = None
    
    def __post_init__(self):
        if self.task_id is None:
            self.task_id = f"{self.user_id}_{int(time.time())}"

@dataclass
class MemorySearchResult:
    """記憶搜索結果"""
    task_id: str
    success: bool
    results: List[Any] = None
    context: str = ""
    execution_time: float = 0.0
    error: Optional[Exception] = None
    cached: bool = False

class AsyncMemoryOptimizer:
    """異步記憶優化器"""
    
    def __init__(self, memory_manager: MemoryManager, max_workers: int = 2, max_results_retention: int = 100):
        """初始化異步記憶優化器
        
        Args:
            memory_manager: 記憶管理器實例
            max_workers: 最大並行工作者數量
            max_results_retention: 最大結果保留數量
        """
        self.memory_manager = memory_manager
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.logger = logging.getLogger(__name__)
        
        # 任務追蹤和結果管理
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.completed_results: Dict[str, MemorySearchResult] = {}
        self.max_results_retention = max_results_retention
        self.result_access_times: Dict[str, float] = {}  # 結果存取時間追蹤
        
        # 統計資訊
        self.total_searches = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_search_time = 0.0
        
        # 預載入設定
        self.preload_enabled = True
        self.preload_cache_size = 50
        self.common_queries_cache: Dict[str, List[Any]] = {}
        
        # 自動清理設定
        self.auto_cleanup_enabled = True
        self.cleanup_threshold = max(int(max_results_retention * 0.8), 1)  # 80% 時開始清理
    
    async def start_memory_search(self, search_task: MemorySearchTask) -> str:
        """啟動異步記憶搜索
        
        Args:
            search_task: 搜索任務
            
        Returns:
            str: 任務ID
        """
        try:
            # 檢查快取
            cached_result = memory_search_cache.get_search_result(
                search_task.query, 
                search_task.user_id, 
                search_task.search_type.value
            )
            
            if cached_result is not None:
                self.cache_hits += 1
                result = MemorySearchResult(
                    task_id=search_task.task_id,
                    success=True,
                    results=cached_result.get('results', []),
                    context=cached_result.get('context', ''),
                    execution_time=0.0,
                    cached=True
                )
                self.completed_results[search_task.task_id] = result
                self.logger.debug(f"記憶搜索快取命中: {search_task.task_id}")
                return search_task.task_id
            
            self.cache_misses += 1
            
            # 創建異步任務
            task = asyncio.create_task(self._execute_memory_search(search_task))
            self.active_tasks[search_task.task_id] = task
            
            self.logger.debug(f"啟動記憶搜索任務: {search_task.task_id}")
            return search_task.task_id
            
        except Exception as e:
            self.logger.error(f"啟動記憶搜索失敗: {str(e)}")
            error_result = MemorySearchResult(
                task_id=search_task.task_id,
                success=False,
                error=e
            )
            self.completed_results[search_task.task_id] = error_result
            return search_task.task_id
    
    async def _execute_memory_search(self, search_task: MemorySearchTask) -> MemorySearchResult:
        """執行記憶搜索
        
        Args:
            search_task: 搜索任務
            
        Returns:
            搜索結果
        """
        start_time = time.time()
        
        try:
            self.logger.debug(f"執行記憶搜索: {search_task.task_id}")
            
            # 在執行器中運行記憶搜索
            loop = asyncio.get_event_loop()
            
            # 創建搜索查詢
            search_query = SearchQuery(
                query=search_task.query,
                search_type=search_task.search_type,
                limit=search_task.limit,
                threshold=search_task.threshold
            )
            
            # 執行搜索
            search_results = await loop.run_in_executor(
                self.executor,
                lambda: self.memory_manager.search_memories(
                    user_id=search_task.user_id,
                    search_query=search_query
                )
            )
            
            # 構建上下文
            context = ""
            if search_task.include_context and search_results:
                context = self._build_context_from_results(search_results)
            
            execution_time = time.time() - start_time
            
            result = MemorySearchResult(
                task_id=search_task.task_id,
                success=True,
                results=search_results,
                context=context,
                execution_time=execution_time
            )
            
            # 快取結果
            cache_data = {
                'results': search_results,
                'context': context,
                'timestamp': time.time()
            }
            
            memory_search_cache.cache_search_result(
                search_task.query,
                search_task.user_id,
                cache_data,
                search_task.search_type.value
            )
            
            self.total_searches += 1
            self.total_search_time += execution_time
            
            self.logger.debug(f"記憶搜索完成: {search_task.task_id}, 耗時: {execution_time:.2f}s")
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"記憶搜索失敗: {search_task.task_id}, 錯誤: {str(e)}")
            
            return MemorySearchResult(
                task_id=search_task.task_id,
                success=False,
                error=e,
                execution_time=execution_time
            )
        
        finally:
            # 清理活動任務
            if search_task.task_id in self.active_tasks:
                del self.active_tasks[search_task.task_id]
            
            # 檢查是否需要清理完成的結果
            if self.auto_cleanup_enabled and len(self.completed_results) >= self.cleanup_threshold:
                self._cleanup_old_results()
    
    async def get_search_result(self, task_id: str, timeout: float = 30.0) -> Optional[MemorySearchResult]:
        """獲取搜索結果
        
        Args:
            task_id: 任務ID
            timeout: 超時時間
            
        Returns:
            搜索結果或 None
        """
        try:
            # 檢查是否已完成
            if task_id in self.completed_results:
                result = self.completed_results[task_id]
                # 更新存取時間
                self.result_access_times[task_id] = time.time()
                # 清理已完成的結果
                self._remove_completed_result(task_id)
                return result
            
            # 檢查是否在活動任務中
            if task_id in self.active_tasks:
                task = self.active_tasks[task_id]
                
                # 等待任務完成
                try:
                    result = await asyncio.wait_for(task, timeout=timeout)
                    self.completed_results[task_id] = result
                    return result
                except asyncio.TimeoutError:
                    self.logger.warning(f"記憶搜索任務超時: {task_id}")
                    task.cancel()
                    return None
            
            self.logger.warning(f"找不到記憶搜索任務: {task_id}")
            return None
            
        except Exception as e:
            self.logger.error(f"獲取搜索結果失敗: {task_id}, 錯誤: {str(e)}")
            return None
    
    def _build_context_from_results(self, search_results: List[Any]) -> str:
        """從搜索結果構建上下文
        
        Args:
            search_results: 搜索結果列表
            
        Returns:
            構建的上下文字串
        """
        if not search_results:
            return ""
        
        context_parts = []
        
        for i, result in enumerate(search_results[:5]):  # 限制最多5個結果
            try:
                # 提取相關資訊
                content = getattr(result, 'content', str(result))
                timestamp = getattr(result, 'timestamp', 'unknown')
                relevance = getattr(result, 'similarity_score', 0.0)
                
                context_part = f"[記憶 {i+1}] (相關度: {relevance:.2f}) {content[:200]}..."
                context_parts.append(context_part)
                
            except Exception as e:
                self.logger.warning(f"構建上下文時出錯: {str(e)}")
                continue
        
        return "\n".join(context_parts)
    
    async def preload_common_memories(self, user_id: str, common_queries: List[str]) -> int:
        """預載入常用記憶
        
        Args:
            user_id: 用戶ID
            common_queries: 常用查詢列表
            
        Returns:
            成功預載入的數量
        """
        if not self.preload_enabled:
            return 0
        
        preloaded_count = 0
        
        for query in common_queries:
            try:
                # 檢查是否已經快取
                if memory_search_cache.get_search_result(query, user_id) is not None:
                    continue
                
                # 創建預載入任務
                search_task = MemorySearchTask(
                    query=query,
                    user_id=user_id,
                    search_type=SearchType.SEMANTIC,
                    limit=5,
                    include_context=True,
                    task_id=f"preload_{user_id}_{int(time.time())}_{preloaded_count}"
                )
                
                # 啟動搜索
                await self.start_memory_search(search_task)
                preloaded_count += 1
                
                # 避免過度負載
                if preloaded_count >= self.preload_cache_size:
                    break
                    
            except Exception as e:
                self.logger.warning(f"預載入記憶失敗: {query}, 錯誤: {str(e)}")
                continue
        
        self.logger.info(f"預載入了 {preloaded_count} 個常用記憶查詢")
        return preloaded_count
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """獲取優化統計資訊
        
        Returns:
            統計資訊
        """
        total_requests = self.cache_hits + self.cache_misses
        cache_hit_ratio = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        avg_search_time = (
            (self.total_search_time / self.total_searches)
            if self.total_searches > 0 else 0
        )
        
        return {
            'total_searches': self.total_searches,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_hit_ratio': f"{cache_hit_ratio:.2f}%",
            'average_search_time': f"{avg_search_time:.2f}s",
            'active_tasks': len(self.active_tasks),
            'completed_results': len(self.completed_results),
            'preload_enabled': self.preload_enabled,
            'preload_cache_size': self.preload_cache_size
        }
    
    def cleanup_old_results(self, max_age: float = 3600) -> int:
        """清理舊的搜索結果
        
        Args:
            max_age: 最大保留時間（秒）
            
        Returns:
            清理的結果數量
        """
        current_time = time.time()
        old_task_ids = []
        
        for task_id, result in self.completed_results.items():
            # 簡單的年齡估算（基於任務ID中的時間戳）
            try:
                timestamp = int(task_id.split('_')[-1])
                if current_time - timestamp > max_age:
                    old_task_ids.append(task_id)
            except (ValueError, IndexError):
                # 如果無法解析時間戳，保留結果
                continue
        
        for task_id in old_task_ids:
            self._remove_completed_result(task_id)
        
        if old_task_ids:
            self.logger.debug(f"清理了 {len(old_task_ids)} 個舊的搜索結果")
        
        return len(old_task_ids)
    
    def _remove_completed_result(self, task_id: str) -> None:
        """移除完成的結果及其存取時間記錄
        
        Args:
            task_id: 任務ID
        """
        if task_id in self.completed_results:
            del self.completed_results[task_id]
        if task_id in self.result_access_times:
            del self.result_access_times[task_id]
    
    def _cleanup_old_results(self) -> int:
        """清理舊的完成結果（LRU策略）
        
        Returns:
            int: 清理的結果數量
        """
        cleaned_count = 0
        
        try:
            # 如果結果數量未超過限制，不執行清理
            if len(self.completed_results) < self.cleanup_threshold:
                return 0
            
            # 計算需要清理的數量（清理到最大限制的60%）
            target_count = max(int(self.max_results_retention * 0.6), 1)
            cleanup_count = len(self.completed_results) - target_count
            
            if cleanup_count <= 0:
                return 0
            
            # 按存取時間排序，清理最舊的結果
            result_items = []
            for task_id in self.completed_results.keys():
                access_time = self.result_access_times.get(task_id, 0)
                result_items.append((access_time, task_id))
            
            # 排序（最舊的在前）
            result_items.sort(key=lambda x: x[0])
            
            # 清理最舊的結果
            for i in range(min(cleanup_count, len(result_items))):
                _, task_id = result_items[i]
                self._remove_completed_result(task_id)
                cleaned_count += 1
            
            self.logger.info(f"主動清理了 {cleaned_count} 個最少存取的搜索結果，當前結果數量: {len(self.completed_results)}")
            
        except Exception as e:
            self.logger.error(f"清理舊搜索結果失敗: {str(e)}")
        
        return cleaned_count
    
    def force_cleanup_all_results(self) -> int:
        """強制清理所有完成的結果
        
        Returns:
            int: 清理的結果數量
        """
        cleaned_count = len(self.completed_results)
        self.completed_results.clear()
        self.result_access_times.clear()
        
        self.logger.warning(f"強制清理了所有搜索結果，共 {cleaned_count} 個")
        return cleaned_count
    
    def get_results_info(self) -> Dict[str, Any]:
        """獲取結果管理資訊
        
        Returns:
            Dict[str, Any]: 結果管理統計
        """
        return {
            'completed_results_count': len(self.completed_results),
            'max_retention': self.max_results_retention,
            'cleanup_threshold': self.cleanup_threshold,
            'usage_ratio': len(self.completed_results) / self.max_results_retention if self.max_results_retention > 0 else 0,
            'needs_cleanup': len(self.completed_results) >= self.cleanup_threshold,
            'auto_cleanup_enabled': self.auto_cleanup_enabled
        }
    
    def shutdown(self):
        """關閉優化器"""
        # 取消所有活動任務
        for task in self.active_tasks.values():
            task.cancel()
        
        # 關閉執行器
        if self.executor:
            self.executor.shutdown(wait=True)
        
        self.logger.info("異步記憶優化器已關閉")

# 便捷函數
def create_memory_search_task(query: str, 
                             user_id: str,
                             search_type: SearchType = SearchType.SEMANTIC,
                             limit: int = 10,
                             threshold: float = 0.7,
                             include_context: bool = True) -> MemorySearchTask:
    """便捷函數：創建記憶搜索任務"""
    return MemorySearchTask(
        query=query,
        user_id=user_id,
        search_type=search_type,
        limit=limit,
        threshold=threshold,
        include_context=include_context
    )