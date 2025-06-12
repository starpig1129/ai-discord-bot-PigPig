"""
性能監控模組

整合所有優化功能的監控、統計和管理，提供統一的性能分析介面。
"""

import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    """性能指標資料結構"""
    timestamp: float = field(default_factory=time.time)
    response_time: float = 0.0
    gemini_cache_hits: int = 0
    gemini_cache_misses: int = 0
    processing_cache_hits: int = 0
    processing_cache_misses: int = 0
    memory_cache_hits: int = 0
    memory_cache_misses: int = 0
    parallel_tools_executed: int = 0
    parallel_execution_time: float = 0.0
    memory_search_time: float = 0.0
    api_call_count: int = 0
    api_call_time: float = 0.0
    error_count: int = 0

class PerformanceMonitor:
    """性能監控器"""
    
    def __init__(self, max_history: int = 1000):
        """初始化性能監控器
        
        Args:
            max_history: 最大歷史記錄數量
        """
        self.max_history = max_history
        self.logger = logging.getLogger(__name__)
        
        # 性能歷史記錄
        self.metrics_history: List[PerformanceMetrics] = []
        
        # 當前會話統計
        self.session_start_time = time.time()
        self.total_requests = 0
        self.total_response_time = 0.0
        self.total_errors = 0
        
        # 警告閾值設定
        self.warning_thresholds = {
            'response_time': 10.0,  # 回應時間超過10秒
            'error_rate': 0.1,      # 錯誤率超過10%
            'cache_hit_rate': 0.5,  # 快取命中率低於50%
            'memory_search_time': 5.0  # 記憶搜索超過5秒
        }
        
        # 性能優化建議
        self.optimization_suggestions: List[str] = []
    
    def start_request_tracking(self) -> str:
        """開始追蹤請求
        
        Returns:
            str: 追蹤ID
        """
        tracking_id = f"req_{int(time.time() * 1000)}"
        return tracking_id
    
    def record_metrics(self, metrics: PerformanceMetrics) -> None:
        """記錄性能指標
        
        Args:
            metrics: 性能指標
        """
        # 添加到歷史記錄
        self.metrics_history.append(metrics)
        
        # 限制歷史記錄大小
        if len(self.metrics_history) > self.max_history:
            self.metrics_history.pop(0)
        
        # 更新會話統計
        self.total_requests += 1
        self.total_response_time += metrics.response_time
        self.total_errors += metrics.error_count
        
        # 檢查警告條件
        self._check_performance_warnings(metrics)
        
        self.logger.debug(f"記錄性能指標: 回應時間 {metrics.response_time:.2f}s")
    
    def get_current_stats(self) -> Dict[str, Any]:
        """獲取當前統計資訊
        
        Returns:
            統計資訊字典
        """
        if not self.metrics_history:
            return {"status": "no_data"}
        
        recent_metrics = self.metrics_history[-10:]  # 最近10次請求
        
        # 計算平均值
        avg_response_time = sum(m.response_time for m in recent_metrics) / len(recent_metrics)
        
        # 計算快取命中率
        total_cache_hits = sum(
            m.gemini_cache_hits + m.processing_cache_hits + m.memory_cache_hits
            for m in recent_metrics
        )
        total_cache_requests = sum(
            m.gemini_cache_hits + m.gemini_cache_misses +
            m.processing_cache_hits + m.processing_cache_misses +
            m.memory_cache_hits + m.memory_cache_misses
            for m in recent_metrics
        )
        
        cache_hit_rate = (total_cache_hits / total_cache_requests) if total_cache_requests > 0 else 0
        
        # 計算錯誤率
        total_errors = sum(m.error_count for m in recent_metrics)
        error_rate = total_errors / len(recent_metrics)
        
        # 會話統計
        session_duration = time.time() - self.session_start_time
        session_avg_response_time = (
            self.total_response_time / self.total_requests
            if self.total_requests > 0 else 0
        )
        session_error_rate = self.total_errors / self.total_requests if self.total_requests > 0 else 0
        
        return {
            "current_performance": {
                "average_response_time": f"{avg_response_time:.2f}s",
                "cache_hit_rate": f"{cache_hit_rate * 100:.1f}%",
                "error_rate": f"{error_rate * 100:.1f}%",
                "recent_requests": len(recent_metrics)
            },
            "session_statistics": {
                "duration": f"{session_duration / 3600:.1f}h",
                "total_requests": self.total_requests,
                "average_response_time": f"{session_avg_response_time:.2f}s",
                "error_rate": f"{session_error_rate * 100:.1f}%"
            },
            "optimization_suggestions": self.optimization_suggestions[-5:],  # 最近5個建議
            "last_updated": datetime.now().isoformat()
        }
    
    def get_detailed_analytics(self) -> Dict[str, Any]:
        """獲取詳細分析報告
        
        Returns:
            詳細分析報告
        """
        if not self.metrics_history:
            return {"status": "no_data"}
        
        # 時間範圍分析
        recent_1h = [m for m in self.metrics_history if time.time() - m.timestamp < 3600]
        recent_24h = [m for m in self.metrics_history if time.time() - m.timestamp < 86400]
        
        def analyze_metrics(metrics_list: List[PerformanceMetrics], period_name: str) -> Dict[str, Any]:
            if not metrics_list:
                return {}
            
            response_times = [m.response_time for m in metrics_list]
            api_times = [m.api_call_time for m in metrics_list]
            memory_times = [m.memory_search_time for m in metrics_list]
            
            return {
                f"{period_name}_requests": len(metrics_list),
                f"{period_name}_avg_response_time": f"{sum(response_times) / len(response_times):.2f}s",
                f"{period_name}_max_response_time": f"{max(response_times):.2f}s",
                f"{period_name}_min_response_time": f"{min(response_times):.2f}s",
                f"{period_name}_avg_api_time": f"{sum(api_times) / len(api_times):.2f}s",
                f"{period_name}_avg_memory_time": f"{sum(memory_times) / len(memory_times):.2f}s",
            }
        
        analytics = {
            "overview": {
                "total_recorded_requests": len(self.metrics_history),
                "monitoring_duration": f"{(time.time() - self.session_start_time) / 3600:.1f}h"
            }
        }
        
        # 添加不同時間範圍的分析
        analytics.update(analyze_metrics(recent_1h, "1h"))
        analytics.update(analyze_metrics(recent_24h, "24h"))
        analytics.update(analyze_metrics(self.metrics_history, "all_time"))
        
        # 快取效能分析
        if recent_1h:
            gemini_hits = sum(m.gemini_cache_hits for m in recent_1h)
            gemini_misses = sum(m.gemini_cache_misses for m in recent_1h)
            gemini_total = gemini_hits + gemini_misses
            
            processing_hits = sum(m.processing_cache_hits for m in recent_1h)
            processing_misses = sum(m.processing_cache_misses for m in recent_1h)
            processing_total = processing_hits + processing_misses
            
            memory_hits = sum(m.memory_cache_hits for m in recent_1h)
            memory_misses = sum(m.memory_cache_misses for m in recent_1h)
            memory_total = memory_hits + memory_misses
            
            analytics["cache_performance"] = {
                "gemini_cache_hit_rate": f"{(gemini_hits / gemini_total * 100):.1f}%" if gemini_total > 0 else "N/A",
                "processing_cache_hit_rate": f"{(processing_hits / processing_total * 100):.1f}%" if processing_total > 0 else "N/A",
                "memory_cache_hit_rate": f"{(memory_hits / memory_total * 100):.1f}%" if memory_total > 0 else "N/A"
            }
        
        return analytics
    
    def _check_performance_warnings(self, metrics: PerformanceMetrics) -> None:
        """檢查性能警告條件
        
        Args:
            metrics: 當前性能指標
        """
        suggestions = []
        
        # 檢查回應時間
        if metrics.response_time > self.warning_thresholds['response_time']:
            suggestions.append(f"回應時間過長 ({metrics.response_time:.1f}s)，建議檢查API調用和記憶搜索效率")
        
        # 檢查記憶搜索時間
        if metrics.memory_search_time > self.warning_thresholds['memory_search_time']:
            suggestions.append(f"記憶搜索耗時過長 ({metrics.memory_search_time:.1f}s)，建議啟用預載入或優化索引")
        
        # 檢查快取命中率
        total_cache_requests = (
            metrics.gemini_cache_hits + metrics.gemini_cache_misses +
            metrics.processing_cache_hits + metrics.processing_cache_misses +
            metrics.memory_cache_hits + metrics.memory_cache_misses
        )
        
        if total_cache_requests > 0:
            total_cache_hits = (
                metrics.gemini_cache_hits + 
                metrics.processing_cache_hits + 
                metrics.memory_cache_hits
            )
            cache_hit_rate = total_cache_hits / total_cache_requests
            
            if cache_hit_rate < self.warning_thresholds['cache_hit_rate']:
                suggestions.append(f"快取命中率偏低 ({cache_hit_rate * 100:.1f}%)，建議調整快取策略或TTL設定")
        
        # 檢查錯誤率
        if len(self.metrics_history) >= 10:
            recent_errors = sum(m.error_count for m in self.metrics_history[-10:])
            error_rate = recent_errors / 10
            
            if error_rate > self.warning_thresholds['error_rate']:
                suggestions.append(f"錯誤率偏高 ({error_rate * 100:.1f}%)，請檢查系統穩定性")
        
        # 添加建議到列表
        for suggestion in suggestions:
            if suggestion not in self.optimization_suggestions:
                self.optimization_suggestions.append(suggestion)
                self.logger.warning(f"性能警告: {suggestion}")
        
        # 限制建議列表大小
        if len(self.optimization_suggestions) > 20:
            self.optimization_suggestions = self.optimization_suggestions[-20:]
    
    def generate_performance_report(self) -> str:
        """生成性能報告
        
        Returns:
            格式化的性能報告字串
        """
        stats = self.get_current_stats()
        analytics = self.get_detailed_analytics()
        
        report_lines = [
            "=== Discord 機器人性能報告 ===",
            f"生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "📊 當前性能指標:",
            f"  • 平均回應時間: {stats['current_performance']['average_response_time']}",
            f"  • 快取命中率: {stats['current_performance']['cache_hit_rate']}",
            f"  • 錯誤率: {stats['current_performance']['error_rate']}",
            "",
            "📈 會話統計:",
            f"  • 運行時間: {stats['session_statistics']['duration']}",
            f"  • 總請求數: {stats['session_statistics']['total_requests']}",
            f"  • 平均回應時間: {stats['session_statistics']['average_response_time']}",
            "",
        ]
        
        if analytics.get("cache_performance"):
            report_lines.extend([
                "🚀 快取性能 (最近1小時):",
                f"  • Gemini API 快取: {analytics['cache_performance']['gemini_cache_hit_rate']}",
                f"  • 處理結果快取: {analytics['cache_performance']['processing_cache_hit_rate']}",
                f"  • 記憶搜索快取: {analytics['cache_performance']['memory_cache_hit_rate']}",
                ""
            ])
        
        if stats.get("optimization_suggestions"):
            report_lines.extend([
                "⚠️  優化建議:",
                *[f"  • {suggestion}" for suggestion in stats["optimization_suggestions"]],
                ""
            ])
        
        report_lines.append("=== 報告結束 ===")
        
        return "\n".join(report_lines)
    
    def export_metrics(self, filepath: str = None) -> str:
        """匯出性能指標到JSON檔案
        
        Args:
            filepath: 匯出檔案路徑
            
        Returns:
            匯出檔案路徑
        """
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"performance_metrics_{timestamp}.json"
        
        export_data = {
            "export_time": datetime.now().isoformat(),
            "session_info": {
                "start_time": self.session_start_time,
                "total_requests": self.total_requests,
                "total_response_time": self.total_response_time,
                "total_errors": self.total_errors
            },
            "metrics_history": [
                {
                    "timestamp": m.timestamp,
                    "response_time": m.response_time,
                    "gemini_cache_hits": m.gemini_cache_hits,
                    "gemini_cache_misses": m.gemini_cache_misses,
                    "processing_cache_hits": m.processing_cache_hits,
                    "processing_cache_misses": m.processing_cache_misses,
                    "memory_cache_hits": m.memory_cache_hits,
                    "memory_cache_misses": m.memory_cache_misses,
                    "parallel_tools_executed": m.parallel_tools_executed,
                    "parallel_execution_time": m.parallel_execution_time,
                    "memory_search_time": m.memory_search_time,
                    "api_call_count": m.api_call_count,
                    "api_call_time": m.api_call_time,
                    "error_count": m.error_count
                }
                for m in self.metrics_history
            ],
            "optimization_suggestions": self.optimization_suggestions
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"性能指標已匯出至: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"匯出性能指標失敗: {str(e)}")
            raise
    
    def reset_metrics(self) -> None:
        """重置所有性能指標"""
        self.metrics_history.clear()
        self.session_start_time = time.time()
        self.total_requests = 0
        self.total_response_time = 0.0
        self.total_errors = 0
        self.optimization_suggestions.clear()
        
        self.logger.info("性能指標已重置")

# 全域性能監控器實例
performance_monitor = PerformanceMonitor()

# 便捷函數
def record_performance_metrics(metrics: PerformanceMetrics) -> None:
    """便捷函數：記錄性能指標"""
    performance_monitor.record_metrics(metrics)

def get_performance_stats() -> Dict[str, Any]:
    """便捷函數：獲取性能統計"""
    return performance_monitor.get_current_stats()

def get_performance_report() -> str:
    """便捷函數：獲取性能報告"""
    return performance_monitor.generate_performance_report()

def create_performance_metrics(**kwargs) -> PerformanceMetrics:
    """便捷函數：創建性能指標"""
    return PerformanceMetrics(**kwargs)