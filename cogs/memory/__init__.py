"""Discord Bot 永久頻道記憶系統模組

本模組實作基於 SQLite + FAISS 混合架構的永久頻道記憶系統，
支援高效的語義搜尋、關鍵字搜尋和時間篩選功能。
整合 Qwen3-Embedding-0.6B 和 Qwen3-Reranker-0.6B 模型。

主要模組：
- memory_manager: 記憶管理核心類別
- database: 資料庫操作類別
- config: 配置管理
- embedding_service: Qwen3 嵌入服務
- reranker_service: Qwen3 重排序服務
- search_engine: 搜尋引擎
- vector_manager: 向量管理
- startup_logger: 啟動日誌優化管理器
- exceptions: 自定義例外類別
"""

from .memory_manager import MemoryManager
from .database import DatabaseManager
from .config import MemoryConfig, MemoryProfile, HardwareDetector
from .embedding_service import EmbeddingService, embedding_service_manager
from .reranker_service import RerankerService
from .fallback_memory_manager import FallbackMemoryManager
from .vector_manager import VectorManager
from .search_engine import SearchEngine, SearchQuery, SearchResult, SearchType, TimeRange
from .startup_logger import StartupLogger, StartupLoggerManager, get_startup_logger
from .exceptions import (
    MemorySystemError,
    DatabaseError,
    ConfigurationError,
    HardwareIncompatibleError,
    SearchError,
    VectorOperationError
)

__version__ = "2.0.0"

__all__ = [
    # 核心類別
    "MemoryManager",
    "DatabaseManager",
    "MemoryConfig",
    "MemoryProfile",
    "HardwareDetector",
    
    # 嵌入和重排序服務
    "EmbeddingService",
    "embedding_service_manager",
    "RerankerService",
    
    # 備用記憶體管理
    "FallbackMemoryManager",
    # 向量管理
    "VectorManager",
    
    # 搜尋引擎
    "SearchEngine",
    "SearchQuery",
    "SearchResult",
    "SearchType",
    "TimeRange",
    
    # 啟動日誌管理
    "StartupLogger",
    "StartupLoggerManager",
    "get_startup_logger",
    
    # 例外類別
    "MemorySystemError",
    "DatabaseError",
    "ConfigurationError",
    "HardwareIncompatibleError",
    "SearchError",
    "VectorOperationError"
]