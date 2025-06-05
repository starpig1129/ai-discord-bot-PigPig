"""
頻道系統提示管理模組

此模組提供完整的頻道系統提示管理功能，包含：
- 三層繼承機制（全域 → 伺服器 → 頻道）
- Discord 斜線命令介面
- 權限管理
- UI 元件
- 快取系統

版本: 1.0.0
"""

from .manager import SystemPromptManager
from .commands import SystemPromptCommands
from .permissions import PermissionValidator
from .exceptions import (
    SystemPromptError,
    PermissionError,
    ValidationError,
    ConfigurationError
)

__version__ = "1.0.0"

__all__ = [
    'SystemPromptManager',
    'SystemPromptCommands',
    'PermissionValidator',
    'SystemPromptError',
    'PermissionError',
    'ValidationError',
    'ConfigurationError'
]