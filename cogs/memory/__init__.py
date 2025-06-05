"""Discord Bot 永久頻道記憶系統模組

本模組實作基於 SQLite + FAISS 混合架構的永久頻道記憶系統，
支援高效的語義搜尋、關鍵字搜尋和時間篩選功能。

主要模組：
- memory_manager: 記憶管理核心類別
- database: 資料庫操作類別  
- config: 配置管理
- exceptions: 自定義例外類別
"""

from .memory_manager import MemoryManager
from .database import DatabaseManager
from .config import MemoryConfig
from .exceptions import (
    MemorySystemError,
    DatabaseError,
    ConfigurationError,
    HardwareIncompatibleError
)

__version__ = "1.0.0"

__all__ = [
    "MemoryManager",
    "DatabaseManager", 
    "MemoryConfig",
    "MemorySystemError",
    "DatabaseError",
    "ConfigurationError",
    "HardwareIncompatibleError"
]