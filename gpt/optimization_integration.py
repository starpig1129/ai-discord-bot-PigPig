"""
優化功能整合模組

統一管理和協調所有性能優化功能，提供簡化的整合介面。
包含GPU記憶體監控和自動清理機制。
"""

import asyncio
import logging
import time
import gc
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass

# 導入GPU相關模組
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# 導入所有優化模組
from gpt.core.response_generator import generate_response
from gpt.cache_utils import  cleanup_caches
from gpt.processing_cache import (
    processing_cache, memory_search_cache
)
from gpt.parallel_tool_manager import (
    ParallelToolManager, ToolRequest, create_tool_request,
    execute_tools_in_parallel
)
from gpt.performance_monitor import (
    PerformanceMonitor
)
from gpt.optimization_config_manager import (
    get_optimization_settings,
    OptimizationSettings
)

logger = logging.getLogger(__name__)

@dataclass
class OptimizationConfig:
    """優化配置（向後兼容性）"""
    enable_gemini_cache: bool = True
    enable_processing_cache: bool = True
    enable_memory_cache: bool = True
    enable_parallel_tools: bool = True
    enable_performance_monitoring: bool = True
    
    gemini_cache_ttl: str = "3600s"
    processing_cache_ttl: int = 300
    memory_cache_ttl: int = 1800
    
    max_parallel_workers: int = 4
    tool_timeout: float = 30.0
    
    auto_cleanup_interval: int = 3600  # 1小時
    
    @classmethod
    def from_settings(cls, settings: OptimizationSettings) -> 'OptimizationConfig':
        """從 OptimizationSettings 創建 OptimizationConfig"""
        return cls(
            enable_gemini_cache=settings.enable_gemini_cache,
            enable_processing_cache=settings.enable_processing_cache,
            enable_memory_cache=settings.enable_memory_cache,
            enable_parallel_tools=settings.enable_parallel_tools,
            enable_performance_monitoring=settings.enable_performance_monitoring,
            gemini_cache_ttl=settings.gemini_cache_ttl,
            processing_cache_ttl=settings.processing_cache_ttl,
            memory_cache_ttl=settings.memory_cache_ttl,
            max_parallel_workers=settings.max_parallel_workers,
            tool_timeout=settings.tool_default_timeout,
            auto_cleanup_interval=settings.auto_cleanup_interval
        )

class OptimizedDiscordBot:
    """優化的 Discord 機器人處理器"""
    
    def __init__(self, config: OptimizationConfig = None):
        """初始化優化處理器
        
        Args:
            config: 優化配置
        """
        self.config = config or OptimizationConfig()
        self.logger = logging.getLogger(__name__)
        
        # 初始化各個優化組件
        self.parallel_tool_manager = ParallelToolManager(
            max_workers=self.config.max_parallel_workers,
            default_timeout=self.config.tool_timeout
        ) if self.config.enable_parallel_tools else None
        
        self.performance_monitor = PerformanceMonitor() if self.config.enable_performance_monitoring else None
        
        # 上次清理時間
        self.last_cleanup = time.time()
        
        self.logger.info("優化 Discord 機器人處理器初始化完成")
    
    async def process_user_input(self, 
                                user_input: str,
                                user_id: str,
                                channel_id: str,
                                system_prompt: str,
                                dialogue_history: Optional[List[Dict]] = None,
                                image_input: Any = None,
                                audio_input: Any = None,
                                video_input: Any = None) -> Tuple[Any, Any]:
        """優化的用戶輸入處理
        
        Args:
            user_input: 用戶輸入
            user_id: 用戶ID
            channel_id: 頻道ID
            system_prompt: 系統提示
            dialogue_history: 對話歷史
            image_input: 圖片輸入
            audio_input: 音訊輸入
            video_input: 影片輸入
            
        Returns:
            處理結果和異步生成器
        """
        if self.performance_monitor:
            self.performance_monitor.start_timer('process_user_input')

        try:
            # 自動清理檢查
            await self._auto_cleanup_check()
            
            # Step 1: 檢查處理結果快取
            cached_result = None
            if self.config.enable_processing_cache:
                cached_result = processing_cache.get_cached_result(
                    user_input, user_id, channel_id, system_prompt
                )
                if cached_result is not None:
                    if self.performance_monitor:
                        self.performance_monitor.increment_counter('processing_cache_hits')
                        self.performance_monitor.stop_timer('process_user_input')
                    
                    self.logger.info("使用處理結果快取")
                    return cached_result
                else:
                    if self.performance_monitor:
                        self.performance_monitor.increment_counter('processing_cache_misses')
            
            # Step 2: 啟動異步記憶搜索（如果啟用）
            memory_search_task = None
            if self.config.enable_memory_cache and dialogue_history:
                if self.performance_monitor:
                    self.performance_monitor.start_timer('memory_search')
                memory_search_task = self._start_memory_search(user_input, user_id)
            
            # Step 3: 準備並行工具執行（如果需要）
            tool_results = {}
            if self.config.enable_parallel_tools:
                # 這裡可以根據具體需求分析用戶輸入，決定需要執行哪些工具
                tool_requests = self._analyze_tool_requirements(user_input, user_id, channel_id)
                if tool_requests:
                    if self.performance_monitor:
                        self.performance_monitor.start_timer('parallel_tool_execution')
                    tool_results = await execute_tools_in_parallel(tool_requests)
                    if self.performance_monitor:
                        self.performance_monitor.stop_timer('parallel_tool_execution')
                        self.performance_monitor.increment_counter('parallel_tools_executed', len(tool_requests))
            
            # Step 4: 獲取記憶搜索結果
            memory_context = ""
            if memory_search_task:
                memory_result = await memory_search_task
                if self.performance_monitor:
                    self.performance_monitor.stop_timer('memory_search')
                
                if memory_result and memory_result.get('context'):
                    memory_context = memory_result['context']
                    if self.performance_monitor:
                        self.performance_monitor.increment_counter('memory_cache_hits')
                else:
                    if self.performance_monitor:
                        self.performance_monitor.increment_counter('memory_cache_misses')
            
            # Step 5: 整合上下文並使用快取生成回應
            enhanced_system_prompt = self._build_enhanced_system_prompt(
                system_prompt, memory_context, tool_results
            )
            
            if self.performance_monitor:
                self.performance_monitor.start_timer('api_call')
            result, response_generator = await generate_response(
                inst=user_input,
                system_prompt=enhanced_system_prompt,
                dialogue_history=dialogue_history,
                image_input=image_input,
                audio_input=audio_input,
                video_input=video_input
            )
            if self.performance_monitor:
                self.performance_monitor.stop_timer('api_call')
                self.performance_monitor.increment_counter('api_call_count')
            
            # 如果使用了 Gemini 快取
            if self.config.enable_gemini_cache:
                if self.performance_monitor:
                    self.performance_monitor.increment_counter('gemini_cache_hits')  # 簡化處理
            else:
                if self.performance_monitor:
                    self.performance_monitor.increment_counter('gemini_cache_misses')
            
            # Step 6: 快取處理結果
            if self.config.enable_processing_cache:
                processing_cache.cache_result(
                    user_input, user_id, channel_id,
                    (result, response_generator), system_prompt
                )
            
            # Step 7: 記錄性能指標 (已透過計時器完成)
            if self.performance_monitor:
                self.performance_monitor.stop_timer('process_user_input')
            
            self.logger.info(f"優化處理完成")
            
            return result, response_generator
            
        except Exception as e:
            if self.performance_monitor:
                self.performance_monitor.increment_counter('error_count')
                self.performance_monitor.stop_timer('process_user_input')
            
            self.logger.error(f"優化處理失敗: {str(e)}")
            raise
    
    async def _start_memory_search(self, query: str, user_id: str) -> Optional[Dict]:
        """啟動異步記憶搜索
        
        Args:
            query: 搜索查詢
            user_id: 用戶ID
            
        Returns:
            搜索結果或 None
        """
        try:
            # 檢查記憶搜索快取
            cached_memory = memory_search_cache.get_search_result(query, user_id)
            if cached_memory:
                return cached_memory
            
            # 這裡應該整合實際的記憶搜索功能
            # 目前返回空結果作為佔位符
            self.logger.debug(f"啟動記憶搜索: {query[:50]}...")
            
            # 模擬異步搜索
            await asyncio.sleep(0.1)
            
            # 實際實現時，這裡應該調用記憶管理器的搜索功能
            search_result = {
                'context': '',
                'results': [],
                'timestamp': time.time()
            }
            
            # 快取搜索結果
            memory_search_cache.cache_search_result(query, user_id, search_result)
            
            return search_result
            
        except Exception as e:
            self.logger.error(f"記憶搜索失敗: {str(e)}")
            return None
    
    def _analyze_tool_requirements(self, 
                                 user_input: str, 
                                 user_id: str, 
                                 channel_id: str) -> List[ToolRequest]:
        """分析工具需求
        
        Args:
            user_input: 用戶輸入
            user_id: 用戶ID
            channel_id: 頻道ID
            
        Returns:
            工具請求列表
        """
        tool_requests = []
        
        # 簡化的工具需求分析
        # 實際實現時應該整合 choose_act.py 的邏輯
        
        if any(keyword in user_input.lower() for keyword in ['搜索', '查找', 'search']):
            # 需要網路搜索工具
            tool_requests.append(create_tool_request(
                tool_name='internet_search',
                function=lambda: {"result": "搜索結果佔位符"},
                priority=1,
                timeout=15.0
            ))
        
        if any(keyword in user_input.lower() for keyword in ['計算', '數學', 'calculate']):
            # 需要計算工具
            tool_requests.append(create_tool_request(
                tool_name='calculate',
                function=lambda: {"result": "計算結果佔位符"},
                priority=2,
                timeout=10.0
            ))
        
        return tool_requests
    
    def _build_enhanced_system_prompt(self, 
                                    original_prompt: str,
                                    memory_context: str,
                                    tool_results: Dict[str, Any]) -> str:
        """構建增強的系統提示
        
        Args:
            original_prompt: 原始系統提示
            memory_context: 記憶上下文
            tool_results: 工具結果
            
        Returns:
            增強的系統提示
        """
        enhanced_parts = [original_prompt]
        
        if memory_context:
            enhanced_parts.append(f"\n=== 相關記憶 ===\n{memory_context}")
        
        if tool_results:
            tool_context = "\n=== 工具執行結果 ==="
            for tool_name, result in tool_results.items():
                if hasattr(result, 'result') and result.result:
                    tool_context += f"\n{tool_name}: {result.result}"
            enhanced_parts.append(tool_context)
        
        return "\n".join(enhanced_parts)
    
    async def _auto_cleanup_check(self) -> None:
        """自動清理檢查"""
        current_time = time.time()
        
        if current_time - self.last_cleanup > self.config.auto_cleanup_interval:
            self.logger.info("執行自動清理...")
            
            # 清理各種快取
            cleanup_count = cleanup_caches()
            
            # 檢查GPU記憶體使用情況並執行清理
            gpu_usage = await self._check_gpu_memory_usage()
            if gpu_usage > 75.0:  # 如果GPU使用率超過75%
                await self._gpu_memory_cleanup()
                self.logger.info(f"執行GPU記憶體清理，使用率: {gpu_usage:.1f}%")
            
            self.last_cleanup = current_time
            self.logger.info(f"自動清理完成，清理了 {cleanup_count} 個項目")
    
    async def _check_gpu_memory_usage(self) -> float:
        """檢查GPU記憶體使用率
        
        Returns:
            float: GPU記憶體使用率百分比
        """
        try:
            if not TORCH_AVAILABLE or not torch.cuda.is_available():
                return 0.0
            
            total_memory = torch.cuda.get_device_properties(0).total_memory
            allocated_memory = torch.cuda.memory_allocated(0)
            usage_percent = (allocated_memory / total_memory) * 100
            
            return usage_percent
            
        except Exception as e:
            self.logger.warning(f"檢查GPU記憶體使用率失敗: {e}")
            return 0.0
    
    async def _gpu_memory_cleanup(self) -> None:
        """GPU記憶體清理"""
        try:
            if TORCH_AVAILABLE and torch.cuda.is_available():
                # 清理PyTorch GPU快取
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                
                # 強制垃圾回收
                gc.collect()
                
                # 再次清理
                torch.cuda.empty_cache()
                
                self.logger.info("GPU記憶體清理完成")
            
        except Exception as e:
            self.logger.error(f"GPU記憶體清理失敗: {e}")
    
    def get_optimization_status(self) -> Dict[str, Any]:
        """獲取優化狀態
        
        Returns:
            優化狀態資訊
        """
        status = {
            "config": {
                "gemini_cache": self.config.enable_gemini_cache,
                "processing_cache": self.config.enable_processing_cache,
                "memory_cache": self.config.enable_memory_cache,
                "parallel_tools": self.config.enable_parallel_tools,
                "performance_monitoring": self.config.enable_performance_monitoring
            },
            "last_cleanup": self.last_cleanup,
            "uptime": time.time() - self.last_cleanup
        }
        
        # 添加GPU記憶體狀態
        try:
            gpu_usage = asyncio.create_task(self._check_gpu_memory_usage())
            # 注意：這裡簡化處理，實際使用時建議改為同步版本
            status["gpu_memory"] = {
                "available": TORCH_AVAILABLE and torch.cuda.is_available() if TORCH_AVAILABLE else False,
                "torch_available": TORCH_AVAILABLE
            }
        except Exception as e:
            status["gpu_memory"] = {"error": str(e)}
        
        # 添加性能統計
        if self.config.enable_performance_monitoring and self.performance_monitor:
            status["performance"] = self.performance_monitor.get_performance_stats()
        
        # 添加工具執行統計
        if self.parallel_tool_manager:
            status["tool_execution"] = self.parallel_tool_manager.get_execution_stats()
        
        return status
    
    def get_gpu_memory_info(self) -> Dict[str, Any]:
        """同步獲取GPU記憶體資訊
        
        Returns:
            Dict[str, Any]: GPU記憶體統計
        """
        gpu_info = {
            'torch_available': TORCH_AVAILABLE,
            'cuda_available': False,
            'total_mb': 0,
            'allocated_mb': 0,
            'cached_mb': 0,
            'free_mb': 0,
            'usage_percent': 0.0
        }
        
        try:
            if TORCH_AVAILABLE and torch.cuda.is_available():
                gpu_info['cuda_available'] = True
                gpu_info['total_mb'] = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
                gpu_info['allocated_mb'] = torch.cuda.memory_allocated(0) // (1024 * 1024)
                gpu_info['cached_mb'] = torch.cuda.memory_reserved(0) // (1024 * 1024)
                gpu_info['free_mb'] = gpu_info['total_mb'] - gpu_info['allocated_mb']
                gpu_info['usage_percent'] = (gpu_info['allocated_mb'] / gpu_info['total_mb']) * 100
        except Exception as e:
            gpu_info['error'] = str(e)
        
        return gpu_info
    
    async def shutdown(self) -> None:
        """關閉優化處理器"""
        self.logger.info("正在關閉優化處理器...")
        
        if self.parallel_tool_manager:
            self.parallel_tool_manager.shutdown()
        
        # 執行最後一次清理
        cleanup_caches()
        
        # 執行GPU記憶體清理
        await self._gpu_memory_cleanup()
        
        self.logger.info("優化處理器已關閉")

# 全域優化處理器實例
optimized_bot: Optional[OptimizedDiscordBot] = None

def initialize_optimization(config: OptimizationConfig = None) -> OptimizedDiscordBot:
    """初始化優化系統
    
    Args:
        config: 優化配置（可選，如果不提供將從配置檔案載入）
        
    Returns:
        優化處理器實例
    """
    global optimized_bot
    
    # 如果沒有提供配置，從配置管理器載入
    if config is None:
        try:
            settings = get_optimization_settings()
            config = OptimizationConfig.from_settings(settings)
            logger.info("使用配置檔案初始化優化系統")
        except Exception as e:
            logger.warning(f"載入配置檔案失敗，使用預設配置: {e}")
            config = OptimizationConfig()
    
    optimized_bot = OptimizedDiscordBot(config)
    logger.info("Discord 機器人優化系統已初始化")
    return optimized_bot

def initialize_optimization_from_file(config_path: str = None) -> OptimizedDiscordBot:
    """從配置檔案初始化優化系統
    
    Args:
        config_path: 配置檔案路徑（可選）
        
    Returns:
        優化處理器實例
    """
    try:
        if config_path:
            # 使用指定的配置檔案
            from gpt.optimization_config_manager import OptimizationConfigManager
            config_manager = OptimizationConfigManager(config_path)
            settings = config_manager.get_settings()
        else:
            # 使用預設配置檔案
            settings = get_optimization_settings()
        
        config = OptimizationConfig.from_settings(settings)
        return initialize_optimization(config)
        
    except Exception as e:
        logger.error(f"從配置檔案初始化失敗: {e}")
        # 降級到預設配置
        return initialize_optimization()

def get_optimized_bot() -> Optional[OptimizedDiscordBot]:
    """獲取優化處理器實例"""
    return optimized_bot

# 便捷函數
async def process_optimized_request(user_input: str,
                                  user_id: str,
                                  channel_id: str,
                                  system_prompt: str,
                                  **kwargs) -> Tuple[Any, Any]:
    """便捷函數：處理優化請求"""
    if optimized_bot is None:
        raise RuntimeError("優化系統尚未初始化，請先調用 initialize_optimization()")
    
    return await optimized_bot.process_user_input(
        user_input, user_id, channel_id, system_prompt, **kwargs
    )