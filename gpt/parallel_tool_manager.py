"""
並行工具管理器

用於優化 choose_act.py 中工具調用的並行執行，提升整體響應速度。
實現工具依賴分析和並行執行策略。
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Callable, Set
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from function import func

logger = logging.getLogger(__name__)

class ToolExecutionStatus(Enum):
    """工具執行狀態"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class ToolRequest:
    """工具請求資料結構"""
    tool_name: str
    function: Callable
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    dependencies: Set[str] = None
    priority: int = 0
    timeout: float = 30.0
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = set()

@dataclass
class ToolResult:
    """工具執行結果"""
    tool_name: str
    status: ToolExecutionStatus
    result: Any = None
    error: Optional[Exception] = None
    execution_time: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0

class ParallelToolManager:
    """並行工具管理器"""
    
    def __init__(self, max_workers: int = 4, default_timeout: float = 30.0):
        """初始化並行工具管理器
        
        Args:
            max_workers: 最大並行工作者數量
            default_timeout: 預設超時時間（秒）
        """
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.logger = logging.getLogger(__name__)
        
        # 統計資訊
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0
        self.total_execution_time = 0.0
        
        # 工具依賴關係配置
        self.tool_dependencies = {
            # 搜索相關工具通常獨立
            'internet_search': set(),
            'calculate': set(),
            'gen_img': set(),
            
            # 用戶數據管理可能依賴於其他工具的結果
            'manage_user_data': {'internet_search'},
            
            # 排程管理相對獨立
            'schedule_management': set(),
            'send_reminder': {'schedule_management'},
            
            # 直接回答通常在最後執行
            'directly_answer': {'internet_search', 'calculate', 'manage_user_data'}
        }
    
    def _analyze_dependencies(self, tool_requests: List[ToolRequest]) -> Dict[str, Set[str]]:
        """分析工具依賴關係
        
        Args:
            tool_requests: 工具請求列表
            
        Returns:
            依賴關係映射
        """
        # 更新工具請求的依賴關係
        for request in tool_requests:
            if request.tool_name in self.tool_dependencies:
                # 只保留當前批次中存在的依賴
                available_tools = {req.tool_name for req in tool_requests}
                request.dependencies = self.tool_dependencies[request.tool_name] & available_tools
        
        # 返回依賴映射
        return {req.tool_name: req.dependencies for req in tool_requests}
    
    def _get_execution_groups(self, tool_requests: List[ToolRequest]) -> List[List[ToolRequest]]:
        """將工具請求分組為可並行執行的批次
        
        Args:
            tool_requests: 工具請求列表
            
        Returns:
            按執行順序分組的工具請求列表
        """
        dependencies = self._analyze_dependencies(tool_requests)
        completed = set()
        groups = []
        remaining_requests = tool_requests.copy()
        
        while remaining_requests:
            # 找出當前可以執行的工具（無依賴或依賴已完成）
            ready_requests = []
            still_waiting = []
            
            for request in remaining_requests:
                if request.dependencies.issubset(completed):
                    ready_requests.append(request)
                else:
                    still_waiting.append(request)
            
            if not ready_requests:
                # 如果沒有可執行的工具，可能存在循環依賴
                self.logger.warning("偵測到可能的循環依賴，強制執行剩餘工具")
                ready_requests = still_waiting
                still_waiting = []
            
            # 按優先級排序
            ready_requests.sort(key=lambda x: x.priority, reverse=True)
            groups.append(ready_requests)
            
            # 更新已完成集合和剩餘請求
            completed.update(req.tool_name for req in ready_requests)
            remaining_requests = still_waiting
        
        return groups
    
    async def _execute_tool_async(self, tool_request: ToolRequest) -> ToolResult:
        """異步執行單個工具
        
        Args:
            tool_request: 工具請求
            
        Returns:
            工具執行結果
        """
        start_time = time.time()
        result = ToolResult(
            tool_name=tool_request.tool_name,
            status=ToolExecutionStatus.PENDING,
            start_time=start_time
        )
        
        try:
            self.logger.debug(f"開始執行工具: {tool_request.tool_name}")
            result.status = ToolExecutionStatus.RUNNING
            
            # 在執行器中運行工具函數
            loop = asyncio.get_event_loop()
            
            # 設定超時
            timeout = tool_request.timeout or self.default_timeout
            
            # 執行工具函數
            if asyncio.iscoroutinefunction(tool_request.function):
                # 如果是異步函數
                tool_result = await asyncio.wait_for(
                    tool_request.function(*tool_request.args, **tool_request.kwargs),
                    timeout=timeout
                )
            else:
                # 如果是同步函數，在執行器中運行
                tool_result = await asyncio.wait_for(
                    loop.run_in_executor(
                        self.executor,
                        lambda: tool_request.function(*tool_request.args, **tool_request.kwargs)
                    ),
                    timeout=timeout
                )
            
            result.result = tool_result
            result.status = ToolExecutionStatus.COMPLETED
            self.successful_executions += 1
            
            self.logger.debug(f"工具執行成功: {tool_request.tool_name}")
            
        except asyncio.TimeoutError:
            error_msg = f"工具 {tool_request.tool_name} 執行超時 ({timeout}s)"
            result.error = TimeoutError(error_msg)
            result.status = ToolExecutionStatus.FAILED
            self.failed_executions += 1
            self.logger.error(error_msg)
            
        except Exception as e:
            func.report_error(e, f"tool execution for {tool_request.tool_name}")
            result.error = e
            result.status = ToolExecutionStatus.FAILED
            self.failed_executions += 1
        
        finally:
            end_time = time.time()
            result.end_time = end_time
            result.execution_time = end_time - start_time
            self.total_executions += 1
            self.total_execution_time += result.execution_time
        
        return result
    
    async def execute_tools_parallel(self, tool_requests: List[ToolRequest]) -> Dict[str, ToolResult]:
        """並行執行工具列表
        
        Args:
            tool_requests: 工具請求列表
            
        Returns:
            工具名稱到執行結果的映射
        """
        if not tool_requests:
            return {}
        
        start_time = time.time()
        self.logger.info(f"開始並行執行 {len(tool_requests)} 個工具")
        
        # 分析並分組工具
        execution_groups = self._get_execution_groups(tool_requests)
        
        self.logger.debug(f"工具分為 {len(execution_groups)} 個執行組")
        for i, group in enumerate(execution_groups):
            tool_names = [req.tool_name for req in group]
            self.logger.debug(f"執行組 {i+1}: {tool_names}")
        
        all_results = {}
        
        # 按組順序執行工具
        for group_index, group in enumerate(execution_groups):
            if not group:
                continue
                
            self.logger.debug(f"執行第 {group_index + 1} 組工具")
            
            # 並行執行當前組的所有工具
            tasks = [
                self._execute_tool_async(tool_request)
                for tool_request in group
            ]
            
            # 等待當前組的所有工具完成
            group_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 處理結果
            for result in group_results:
                if isinstance(result, Exception):
                    self.logger.error(f"工具執行異常: {str(result)}")
                    continue
                    
                all_results[result.tool_name] = result
        
        total_time = time.time() - start_time
        self.logger.info(f"所有工具執行完成，總耗時: {total_time:.2f}s")
        
        return all_results
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """獲取執行統計資訊
        
        Returns:
            統計資訊字典
        """
        success_rate = (
            (self.successful_executions / self.total_executions * 100)
            if self.total_executions > 0 else 0
        )
        
        avg_execution_time = (
            (self.total_execution_time / self.total_executions)
            if self.total_executions > 0 else 0
        )
        
        return {
            'total_executions': self.total_executions,
            'successful_executions': self.successful_executions,
            'failed_executions': self.failed_executions,
            'success_rate': f"{success_rate:.2f}%",
            'average_execution_time': f"{avg_execution_time:.2f}s",
            'total_execution_time': f"{self.total_execution_time:.2f}s",
            'max_workers': self.max_workers,
            'default_timeout': self.default_timeout
        }
    
    def reset_stats(self) -> None:
        """重置統計資訊"""
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0
        self.total_execution_time = 0.0
        
    def shutdown(self) -> None:
        """關閉執行器"""
        if self.executor:
            self.executor.shutdown(wait=True)
            self.logger.info("並行工具管理器已關閉")

# 全域並行工具管理器實例
parallel_tool_manager = ParallelToolManager()

# 便捷函數
async def execute_tools_in_parallel(tool_requests: List[ToolRequest]) -> Dict[str, ToolResult]:
    """便捷函數：並行執行工具"""
    return await parallel_tool_manager.execute_tools_parallel(tool_requests)

def create_tool_request(tool_name: str, 
                       function: Callable,
                       args: Tuple = (),
                       kwargs: Dict = None,
                       dependencies: Set[str] = None,
                       priority: int = 0,
                       timeout: float = 30.0) -> ToolRequest:
    """便捷函數：創建工具請求"""
    if kwargs is None:
        kwargs = {}
    if dependencies is None:
        dependencies = set()
        
    return ToolRequest(
        tool_name=tool_name,
        function=function,
        args=args,
        kwargs=kwargs,
        dependencies=dependencies,
        priority=priority,
        timeout=timeout
    )

def get_tool_execution_stats() -> Dict[str, Any]:
    """便捷函數：獲取工具執行統計"""
    return parallel_tool_manager.get_execution_stats()