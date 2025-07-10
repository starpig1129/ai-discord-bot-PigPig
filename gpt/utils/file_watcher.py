import os
import threading
import time
import logging
from typing import Dict, Callable, Set, Any
from datetime import datetime

class FileWatcher:
    """檔案監控和熱重載"""
    
    def __init__(self, check_interval: float = 1.0):
        """
        初始化檔案監控器
        
        Args:
            check_interval: 檢查間隔（秒）
        """
        self.watched_files: Dict[str, datetime] = {}
        self.callbacks: Dict[str, Callable] = {}
        self.check_interval = check_interval
        self._running = False
        self._thread = None
        self._lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
    
    def watch_file(self, path: str, callback: Callable):
        """
        監控檔案變更
        
        Args:
            path: 要監控的檔案路徑
            callback: 檔案變更時的回調函式
        """
        with self._lock:
            if os.path.exists(path):
                self.watched_files[path] = datetime.fromtimestamp(os.path.getmtime(path))
                self.callbacks[path] = callback
                
                self.logger.info(f"Started watching file: {path}")
                
                if not self._running:
                    self._start_watching()
            else:
                self.logger.warning(f"Cannot watch non-existent file: {path}")
    
    def _start_watching(self):
        """開始監控執行緒"""
        with self._lock:
            if not self._running:
                self._running = True
                self._thread = threading.Thread(target=self._watch_loop, daemon=True)
                self._thread.start()
                self.logger.info("File watcher started")
    
    def _watch_loop(self):
        """監控迴圈"""
        while self._running:
            try:
                changes_detected = False
                
                with self._lock:
                    files_to_check = list(self.watched_files.items())
                
                for path, last_mtime in files_to_check:
                    try:
                        if os.path.exists(path):
                            current_mtime = datetime.fromtimestamp(os.path.getmtime(path))
                            
                            if current_mtime > last_mtime:
                                with self._lock:
                                    self.watched_files[path] = current_mtime
                                
                                # 執行回調
                                if path in self.callbacks:
                                    try:
                                        self.logger.info(f"File changed: {path}")
                                        self.callbacks[path](path)
                                        changes_detected = True
                                    except Exception as e:
                                        self.logger.error(f"Error in file watcher callback for {path}: {e}")
                        else:
                            # 檔案被刪除
                            with self._lock:
                                self.watched_files.pop(path, None)
                                self.callbacks.pop(path, None)
                            
                            self.logger.warning(f"Watched file deleted: {path}")
                    
                    except Exception as e:
                        self.logger.error(f"Error checking file {path}: {e}")
                
                if changes_detected:
                    self.logger.debug("File changes detected and processed")
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in file watcher loop: {e}")
                time.sleep(self.check_interval)
    
    def stop_watching(self):
        """停止監控"""
        with self._lock:
            if self._running:
                self._running = False
                self.logger.info("Stopping file watcher...")
                
                if self._thread and self._thread.is_alive():
                    # 等待執行緒結束，但不要無限等待
                    self._thread.join(timeout=2.0)
                    
                    if self._thread.is_alive():
                        self.logger.warning("File watcher thread did not stop gracefully")
                
                self.logger.info("File watcher stopped")
    
    def check_changes(self) -> bool:
        """
        手動檢查變更
        
        Returns:
            bool: 是否檢測到變更
        """
        changes_detected = False
        
        with self._lock:
            files_to_check = list(self.watched_files.items())
        
        for path, last_mtime in files_to_check:
            try:
                if os.path.exists(path):
                    current_mtime = datetime.fromtimestamp(os.path.getmtime(path))
                    
                    if current_mtime > last_mtime:
                        with self._lock:
                            self.watched_files[path] = current_mtime
                        
                        if path in self.callbacks:
                            try:
                                self.callbacks[path](path)
                                changes_detected = True
                            except Exception as e:
                                self.logger.error(f"Error in manual check callback for {path}: {e}")
                else:
                    # 檔案被刪除
                    with self._lock:
                        self.watched_files.pop(path, None)
                        self.callbacks.pop(path, None)
                    
                    self.logger.warning(f"Watched file deleted during manual check: {path}")
            
            except Exception as e:
                self.logger.error(f"Error during manual check of {path}: {e}")
        
        return changes_detected
    
    def add_file(self, path: str, callback: Callable):
        """
        添加要監控的檔案（watch_file 的別名）
        
        Args:
            path: 檔案路徑
            callback: 回調函式
        """
        self.watch_file(path, callback)
    
    def remove_file(self, path: str):
        """
        移除監控檔案
        
        Args:
            path: 要移除的檔案路徑
        """
        with self._lock:
            if path in self.watched_files:
                self.watched_files.pop(path, None)
                self.callbacks.pop(path, None)
                self.logger.info(f"Stopped watching file: {path}")
    
    def get_watched_files(self) -> Set[str]:
        """
        獲取正在監控的檔案列表
        
        Returns:
            正在監控的檔案路徑集合
        """
        with self._lock:
            return set(self.watched_files.keys())
    
    def is_watching(self, path: str) -> bool:
        """
        檢查是否正在監控指定檔案
        
        Args:
            path: 檔案路徑
            
        Returns:
            bool: 是否正在監控
        """
        with self._lock:
            return path in self.watched_files
    
    def get_file_info(self, path: str) -> Dict[str, Any]:
        """
        獲取監控檔案的資訊
        
        Args:
            path: 檔案路徑
            
        Returns:
            檔案資訊字典
        """
        with self._lock:
            if path not in self.watched_files:
                return {}
            
            info = {
                'path': path,
                'last_checked': self.watched_files[path],
                'exists': os.path.exists(path),
                'has_callback': path in self.callbacks
            }
            
            if os.path.exists(path):
                try:
                    stat = os.stat(path)
                    info.update({
                        'size': stat.st_size,
                        'current_mtime': datetime.fromtimestamp(stat.st_mtime)
                    })
                except Exception as e:
                    self.logger.error(f"Error getting file stats for {path}: {e}")
            
            return info
    
    def get_watcher_stats(self) -> Dict[str, Any]:
        """
        獲取監控器統計資訊
        
        Returns:
            統計資訊字典
        """
        with self._lock:
            total_files = len(self.watched_files)
            existing_files = sum(1 for path in self.watched_files.keys() if os.path.exists(path))
            
            return {
                'is_running': self._running,
                'total_watched_files': total_files,
                'existing_files': existing_files,
                'missing_files': total_files - existing_files,
                'check_interval': self.check_interval,
                'thread_alive': self._thread.is_alive() if self._thread else False
            }
    
    def __del__(self):
        """析構函式，確保監控執行緒被正確關閉"""
        self.stop_watching()