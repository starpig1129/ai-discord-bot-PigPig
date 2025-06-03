"""
PigPig Discord Bot 自動更新系統

該模組提供完整的自動更新機制，包括：
- 版本檢查
- 安全下載
- 備份與回滾
- 優雅重啟
- 通知系統
"""

from .manager import UpdateManager
from .checker import VersionChecker
from .downloader import UpdateDownloader
from .security import UpdatePermissionChecker, BackupManager
from .notifier import DiscordNotifier
from .restart import GracefulRestartManager

__all__ = [
    'UpdateManager',
    'VersionChecker', 
    'UpdateDownloader',
    'UpdatePermissionChecker',
    'BackupManager',
    'DiscordNotifier',
    'GracefulRestartManager'
]