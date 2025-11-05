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


class ConfigurationError(MemorySystemError):
    """配置相關錯誤
    
    系統配置載入、驗證、應用等相關錯誤。
    """
    
    def __init__(
        self, 
        message: str, 
        config_key: Optional[str] = None,
        config_value: Optional[Any] = None,
        **kwargs
    ):
        """初始化配置錯誤
        
        Args:
            message: 錯誤訊息
            config_key: 相關的配置鍵
            config_value: 相關的配置值
            **kwargs: 其他上下文資訊
        """
        context = kwargs
        if config_key:
            context['config_key'] = config_key
        if config_value is not None:
            context['config_value'] = str(config_value)
            
        super().__init__(
            message,
            error_code="CONFIG_ERROR", 
            context=context
        )


class HardwareIncompatibleError(MemorySystemError):
    """硬體不相容錯誤
    
    系統硬體不符合記憶系統要求時拋出的錯誤。
    """
    
    def __init__(
        self, 
        message: str,
        required_spec: Optional[dict[str, Any]] = None,
        current_spec: Optional[dict[str, Any]] = None,
        **kwargs
    ):
        """初始化硬體不相容錯誤
        
        Args:
            message: 錯誤訊息
            required_spec: 所需硬體規格
            current_spec: 目前硬體規格
            **kwargs: 其他上下文資訊
        """
        context = kwargs
        if required_spec:
            context['required_spec'] = required_spec
        if current_spec:
            context['current_spec'] = current_spec
            
        super().__init__(
            message,
            error_code="HARDWARE_ERROR",
            context=context
        )


class VectorOperationError(MemorySystemError):
    """向量操作錯誤
    
    FAISS 向量索引操作相關錯誤。
    """
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        channel_id: Optional[str] = None,
        **kwargs
    ):
        """初始化向量操作錯誤
        
        Args:
            message: 錯誤訊息
            operation: 向量操作類型
            channel_id: 相關頻道 ID
            **kwargs: 其他上下文資訊
        """
        context = kwargs
        if operation:
            context['operation'] = operation
        if channel_id:
            context['channel_id'] = channel_id
            
        super().__init__(
            message,
            error_code="VECTOR_ERROR",
            context=context
        )


class IndexIntegrityError(VectorOperationError):
    """索引完整性錯誤
    
    向量索引與 ID 映射不匹配或完整性問題相關錯誤。
    """
    
    def __init__(
        self,
        message: str,
        index_size: Optional[int] = None,
        mapping_size: Optional[int] = None,
        integrity_issues: Optional[list[str]] = None,
        **kwargs
    ):
        """初始化索引完整性錯誤
        
        Args:
            message: 錯誤訊息
            index_size: 索引大小
            mapping_size: 映射大小
            integrity_issues: 完整性問題列表
            **kwargs: 其他上下文資訊
        """
        context = kwargs
        if index_size is not None:
            context['index_size'] = index_size
        if mapping_size is not None:
            context['mapping_size'] = mapping_size
        if integrity_issues:
            context['integrity_issues'] = integrity_issues
            
        super().__init__(
            message,
            operation="integrity_check",
            error_code="INDEX_INTEGRITY_ERROR",
            context=context
        )


class SearchError(MemorySystemError):
    """搜尋操作錯誤
    
    記憶搜尋過程中的錯誤。
    """
    
    def __init__(
        self, 
        message: str,
        search_type: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs
    ):
        """初始化搜尋錯誤
        
        Args:
            message: 錯誤訊息
            search_type: 搜尋類型
            query: 搜尋查詢
            **kwargs: 其他上下文資訊
        """
        context = kwargs
        if search_type:
            context['search_type'] = search_type
        if query:
            context['query'] = query
            
        super().__init__(
            message,
            error_code="SEARCH_ERROR",
            context=context
        )