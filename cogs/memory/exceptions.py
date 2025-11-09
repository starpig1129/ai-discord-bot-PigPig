"""記憶系統自定義例外類別

定義記憶系統中使用的各種例外類別，提供詳細的錯誤訊息和錯誤處理機制。
"""

from typing import Optional, Any


class MemorySystemError(Exception):
    """記憶系統基礎例外類別
    
    所有記憶系統相關例外的基底類別。
    
    Attributes:
        message: 錯誤訊息
        error_code: 錯誤代碼 
        context: 錯誤上下文資訊
    """
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        """初始化記憶系統例外
        
        Args:
            message: 錯誤訊息
            error_code: 錯誤代碼
            context: 錯誤上下文資訊
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
    
    def __str__(self) -> str:
        """返回格式化的錯誤訊息"""
        base_msg = self.message
        if self.error_code:
            base_msg = f"[{self.error_code}] {base_msg}"
        if self.context:
            base_msg += f" | Context: {self.context}"
        return base_msg


class DatabaseError(MemorySystemError):
    """資料庫相關錯誤
    
    資料庫連接、操作、事務處理等相關錯誤。
    """
    
    def __init__(
        self, 
        message: str, 
        operation: Optional[str] = None,
        table: Optional[str] = None,
        **kwargs
    ):
        """初始化資料庫錯誤
        
        Args:
            message: 錯誤訊息
            operation: 執行的資料庫操作
            table: 涉及的資料表
            **kwargs: 其他上下文資訊
        """
        context = kwargs
        if operation:
            context['operation'] = operation
        if table:
            context['table'] = table
            
        super().__init__(
            message, 
            error_code="DB_ERROR",
            context=context
        )

class VectorOperationError(MemorySystemError):
    """Errors related to vector storage operations."""
    pass


class SearchError(MemorySystemError):
    """Errors related to search operations."""
    pass


class IndexIntegrityError(VectorOperationError):
    """Errors related to index integrity."""
    pass