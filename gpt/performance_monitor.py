"""
性能監控模組

整合所有優化功能的監控、統計和管理，提供統一的性能分析介面。
"""

import time
import logging
from collections import defaultdict
from typing import Dict, Any, List, DefaultDict

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """一個簡單的性能監控器，用於追蹤計時器和計數器。"""

    def __init__(self):
        """初始化性能監控器。"""
        self.logger = logging.getLogger(__name__)
        self._timers: DefaultDict[str, List[float]] = defaultdict(list)
        self._counters: DefaultDict[str, int] = defaultdict(int)
        self._timer_starts: Dict[str, float] = {}
        self.session_start_time = time.time()

    def start_timer(self, name: str) -> None:
        """
        啟動一個計時器。

        Args:
            name (str): 計時器的名稱。
        """
        self._timer_starts[name] = time.perf_counter()
        self.logger.debug(f"計時器 '{name}' 已啟動。")

    def stop_timer(self, name: str) -> None:
        """
        停止一個計時器並記錄經過的時間。

        Args:
            name (str): 計時器的名稱。
        """
        if name in self._timer_starts:
            elapsed = time.perf_counter() - self._timer_starts.pop(name)
            self._timers[name].append(elapsed)
            self.logger.debug(f"計時器 '{name}' 已停止。耗時: {elapsed:.4f} 秒。")
        else:
            self.logger.warning(f"試圖停止一個未啟動的計時器: '{name}'")

    def increment_counter(self, name: str, value: int = 1) -> None:
        """
        增加一個計數器的值。

        Args:
            name (str): 計數器的名稱。
            value (int): 要增加的值，預設為 1。
        """
        self._counters[name] += value
        self.logger.debug(f"計數器 '{name}' 已增加 {value}。目前值: {self._counters[name]}")

    def get_performance_stats(self) -> Dict[str, Any]:
        """
        獲取收集到的性能統計數據。

        Returns:
            Dict[str, Any]: 一個包含計時器和計數器統計數據的字典。
        """
        stats: Dict[str, Any] = {
            "timers": {},
            "counters": dict(self._counters),
            "session_duration_seconds": time.time() - self.session_start_time,
        }

        for name, timings in self._timers.items():
            if timings:
                stats["timers"][name] = {
                    "count": len(timings),
                    "total_time": sum(timings),
                    "average_time": sum(timings) / len(timings),
                    "max_time": max(timings),
                    "min_time": min(timings),
                }
            else:
                stats["timers"][name] = {
                    "count": 0,
                    "total_time": 0,
                    "average_time": 0,
                    "max_time": 0,
                    "min_time": 0,
                }
        
        # 計算快取命中率
        cache_hits = self._counters.get("cache_hits", 0)
        cache_misses = self._counters.get("cache_misses", 0)
        total_cache_lookups = cache_hits + cache_misses
        if total_cache_lookups > 0:
            stats["counters"]["cache_hit_rate"] = cache_hits / total_cache_lookups
        else:
            stats["counters"]["cache_hit_rate"] = 0.0

        return stats

    def reset(self) -> None:
        """重置所有計時器和計數器。"""
        self._timers.clear()
        self._counters.clear()
        self._timer_starts.clear()
        self.session_start_time = time.time()
        self.logger.info("性能監控器已重置。")