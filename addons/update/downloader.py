"""
更新下載管理器模組

負責安全地下載更新檔案，包括進度追蹤、檔案驗證和錯誤處理。
"""

import os
import aiohttp
import zipfile
import hashlib
import logging
from datetime import datetime
from typing import Callable, Optional, Awaitable


class UpdateDownloader:
    """更新下載管理器"""
    
    def __init__(self, download_dir: str = "temp/downloads"):
        """
        初始化下載管理器
        
        Args:
            download_dir: 下載目錄路徑
        """
        self.download_dir = download_dir
        self.logger = logging.getLogger(__name__)
        os.makedirs(download_dir, exist_ok=True)
    
    async def download_update(self, 
                            download_url: str, 
                            progress_callback: Optional[Callable[[int], Awaitable[None]]] = None,
                            chunk_size: int = 8192) -> str:
        """
        下載更新檔案
        
        Args:
            download_url: 下載連結
            progress_callback: 進度回調函數
            chunk_size: 下載塊大小
            
        Returns:
            下載的檔案路徑
            
        Raises:
            Exception: 下載過程中的各種錯誤
        """
        filename = f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        filepath = os.path.join(self.download_dir, filename)
        
        self.logger.info(f"開始下載更新檔案: {download_url}")
        
        try:
            timeout = aiohttp.ClientTimeout(total=600)  # 10分鐘超時
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(download_url) as response:
                    if response.status != 200:
                        if response.status == 404:
                            self.logger.error(f"下載URL不存在 (404): {download_url}")
                            raise Exception(f"下載失敗：HTTP 404 - 檔案不存在。請檢查版本號或URL格式")
                        else:
                            self.logger.error(f"下載請求失敗: HTTP {response.status}")
                            raise Exception(f"下載失敗：HTTP {response.status}")
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    self.logger.info(f"檔案大小: {total_size} bytes")
                    
                    with open(filepath, 'wb') as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if progress_callback and total_size > 0:
                                progress = int((downloaded / total_size) * 100)
                                await progress_callback(progress)
                    
                    # 驗證下載的檔案
                    if await self._verify_download(filepath, total_size):
                        self.logger.info(f"檔案下載並驗證成功: {filepath}")
                        return filepath
                    else:
                        raise Exception("下載檔案校驗失敗")
                        
        except aiohttp.ClientError as e:
            self.logger.error(f"網路錯誤: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            raise Exception(f"下載失敗：網路錯誤 - {e}")
        
        except Exception as e:
            self.logger.error(f"下載過程中發生錯誤: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            raise e
    
    async def _verify_download(self, filepath: str, expected_size: int = 0) -> bool:
        """
        驗證下載的檔案
        
        Args:
            filepath: 檔案路徑
            expected_size: 預期檔案大小
            
        Returns:
            驗證是否通過
        """
        try:
            # 檢查檔案是否存在
            if not os.path.exists(filepath):
                self.logger.error("下載的檔案不存在")
                return False
            
            # 檢查檔案大小
            actual_size = os.path.getsize(filepath)
            if actual_size == 0:
                self.logger.error("下載的檔案為空")
                return False
            
            if expected_size > 0 and actual_size != expected_size:
                self.logger.warning(f"檔案大小不符：預期 {expected_size}, 實際 {actual_size}")
                # 不直接返回 False，因為 content-length 可能不準確
            
            # 檢查 ZIP 檔案完整性
            try:
                with zipfile.ZipFile(filepath, 'r') as zip_file:
                    # 測試 ZIP 檔案是否損壞
                    corrupt_file = zip_file.testzip()
                    if corrupt_file:
                        self.logger.error(f"ZIP 檔案損壞，損壞的檔案: {corrupt_file}")
                        return False
                    
                    # 檢查是否包含預期的檔案結構
                    file_list = zip_file.namelist()
                    if not file_list:
                        self.logger.error("ZIP 檔案為空")
                        return False
                    
                    # 檢查是否包含主要的專案檔案
                    expected_files = ['bot.py', 'main.py', 'requirements.txt']
                    found_files = []
                    
                    for expected_file in expected_files:
                        for zip_file_name in file_list:
                            if zip_file_name.endswith(expected_file):
                                found_files.append(expected_file)
                                break
                    
                    if len(found_files) < 2:  # 至少要有2個主要檔案
                        self.logger.warning(f"ZIP 檔案可能不包含完整的專案結構，找到的檔案: {found_files}")
                        # 仍然繼續，但記錄警告
                    
            except zipfile.BadZipFile:
                self.logger.error("檔案不是有效的 ZIP 格式")
                return False
            except Exception as e:
                self.logger.error(f"ZIP 檔案驗證時發生錯誤: {e}")
                return False
            
            self.logger.info("檔案驗證通過")
            return True
            
        except Exception as e:
            self.logger.error(f"檔案驗證時發生未預期錯誤: {e}")
            return False
    
    def calculate_file_hash(self, filepath: str, algorithm: str = 'sha256') -> str:
        """
        計算檔案雜湊值
        
        Args:
            filepath: 檔案路徑
            algorithm: 雜湊演算法
            
        Returns:
            檔案雜湊值
        """
        hash_func = hashlib.new(algorithm)
        
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_func.update(chunk)
            return hash_func.hexdigest()
        except Exception as e:
            self.logger.error(f"計算檔案雜湊值時發生錯誤: {e}")
            return ""
    
    def cleanup_downloads(self, keep_latest: int = 3) -> None:
        """
        清理下載目錄中的舊檔案
        
        Args:
            keep_latest: 保留最新的檔案數量
        """
        try:
            if not os.path.exists(self.download_dir):
                return
            
            # 獲取所有下載檔案並按修改時間排序
            files = []
            for filename in os.listdir(self.download_dir):
                filepath = os.path.join(self.download_dir, filename)
                if os.path.isfile(filepath) and filename.startswith('update_'):
                    files.append((filepath, os.path.getmtime(filepath)))
            
            # 按時間排序，保留最新的檔案
            files.sort(key=lambda x: x[1], reverse=True)
            
            # 刪除過期檔案
            for filepath, _ in files[keep_latest:]:
                try:
                    os.remove(filepath)
                    self.logger.info(f"已刪除舊的下載檔案: {filepath}")
                except Exception as e:
                    self.logger.error(f"刪除檔案時發生錯誤 {filepath}: {e}")
                    
        except Exception as e:
            self.logger.error(f"清理下載目錄時發生錯誤: {e}")
    
    def get_download_dir(self) -> str:
        """
        獲取下載目錄路徑
        
        Returns:
            下載目錄路徑
        """
        return self.download_dir