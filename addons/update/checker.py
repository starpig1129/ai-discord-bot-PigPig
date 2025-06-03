"""
版本檢查器模組

負責檢查 GitHub 上的最新版本並與當前版本進行比較。
"""

import aiohttp
import logging
from typing import Dict, Optional
import update


class VersionChecker:
    """版本檢查器"""
    
    def __init__(self, github_config: Dict[str, str]):
        """
        初始化版本檢查器
        
        Args:
            github_config: GitHub 配置資訊
        """
        self.github_api_url = github_config.get(
            "api_url", 
            "https://api.github.com/repos/PigPig-discord-LLM-bot/releases/latest"
        )
        self.current_version = self._get_current_version()
        self.logger = logging.getLogger(__name__)
    
    def _get_current_version(self) -> str:
        """
        獲取當前版本
        
        Returns:
            當前版本字串
        """
        try:
            return update.__version__
        except AttributeError:
            self.logger.warning("無法從 update.py 獲取版本資訊，使用預設版本")
            return "v1.0.0"
    
    async def check_for_updates(self) -> Dict[str, any]:
        """
        檢查是否有可用更新
        
        Returns:
            包含版本資訊和更新狀態的字典
        """
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.github_api_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        latest_version = data.get("name", self.current_version)
                        
                        # 移除版本號中的 'v' 前綴進行比較
                        current_clean = self.current_version.lstrip('v')
                        latest_clean = latest_version.lstrip('v')
                        
                        # 簡單的版本比較
                        update_available = self._compare_versions(current_clean, latest_clean)
                        
                        return {
                            "current_version": self.current_version,
                            "latest_version": latest_version,
                            "update_available": update_available,
                            "release_notes": data.get("body", ""),
                            "published_at": data.get("published_at", ""),
                            "download_url": f"https://github.com/PigPig-discord-LLM-bot/archive/{latest_version}.zip",
                            "tag_name": data.get("tag_name", latest_version),
                            "prerelease": data.get("prerelease", False)
                        }
                    else:
                        self.logger.error(f"GitHub API 請求失敗: HTTP {response.status}")
                        return self._get_error_result(f"GitHub API 請求失敗: HTTP {response.status}")
                        
        except aiohttp.ClientError as e:
            self.logger.error(f"網路請求錯誤: {e}")
            return self._get_error_result(f"網路請求錯誤: {e}")
        except Exception as e:
            self.logger.error(f"版本檢查時發生未預期錯誤: {e}")
            return self._get_error_result(f"版本檢查錯誤: {e}")
    
    def _compare_versions(self, current: str, latest: str) -> bool:
        """
        比較版本號
        
        Args:
            current: 當前版本
            latest: 最新版本
            
        Returns:
            如果有新版本可用則返回 True
        """
        try:
            # 將版本號分割為數字列表進行比較
            current_parts = [int(x) for x in current.split('.')]
            latest_parts = [int(x) for x in latest.split('.')]
            
            # 補齊較短的版本號
            max_length = max(len(current_parts), len(latest_parts))
            current_parts.extend([0] * (max_length - len(current_parts)))
            latest_parts.extend([0] * (max_length - len(latest_parts)))
            
            # 逐位比較
            for curr, lat in zip(current_parts, latest_parts):
                if lat > curr:
                    return True
                elif lat < curr:
                    return False
            
            return False  # 版本相同
            
        except ValueError:
            # 如果版本號格式不標準，使用字串比較
            self.logger.warning(f"版本號格式不標準，使用字串比較: {current} vs {latest}")
            return latest != current
    
    def _get_error_result(self, error_message: str) -> Dict[str, any]:
        """
        獲取錯誤結果
        
        Args:
            error_message: 錯誤訊息
            
        Returns:
            錯誤結果字典
        """
        return {
            "current_version": self.current_version,
            "latest_version": self.current_version,
            "update_available": False,
            "release_notes": "",
            "published_at": "",
            "download_url": "",
            "error": error_message
        }
    
    def get_current_version(self) -> str:
        """
        獲取當前版本
        
        Returns:
            當前版本字串
        """
        return self.current_version