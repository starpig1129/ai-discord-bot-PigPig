"""
頻道系統提示管理模組的自訂例外類別

定義了所有與系統提示相關的例外狀況，提供明確的錯誤處理機制。
"""

from typing import Optional


class SystemPromptError(Exception):
    """系統提示相關錯誤的基類"""
    
    def __init__(self, message: str, error_code: Optional[str] = None):
        """
        初始化系統提示錯誤
        
        Args:
            message: 錯誤訊息
            error_code: 錯誤代碼（可選）
        """
        super().__init__(message)
        self.error_code = error_code


class PermissionError(SystemPromptError):
    """權限不足錯誤"""
    
    def __init__(self, message: Optional[str] = None, required_permission: Optional[str] = None,
                 lang_manager=None, guild_id: Optional[str] = None):
        """
        初始化權限錯誤
        
        Args:
            message: 錯誤訊息（如果為 None，將使用本地化訊息）
            required_permission: 所需權限（可選）
            lang_manager: 語言管理器（可選）
            guild_id: 伺服器 ID（可選）
        """
        if message is None:
            message = self._get_localized_message("permission_denied", lang_manager, guild_id)
        
        super().__init__(message, "PERMISSION_DENIED")
        self.required_permission = required_permission
    
    def _get_localized_message(self, key: str, lang_manager, guild_id: Optional[str]) -> str:
        """獲取本地化訊息"""
        if lang_manager and guild_id:
            try:
                return lang_manager.translate(guild_id, "commands", "system_prompt", "errors", key)
            except Exception:
                pass
        return "您沒有權限執行此操作"


class ValidationError(SystemPromptError):
    """驗證失敗錯誤"""
    
    def __init__(self, message: Optional[str] = None, field: Optional[str] = None,
                 lang_manager=None, guild_id: Optional[str] = None):
        """
        初始化驗證錯誤
        
        Args:
            message: 錯誤訊息（如果為 None，將使用本地化訊息）
            field: 驗證失敗的欄位（可選）
            lang_manager: 語言管理器（可選）
            guild_id: 伺服器 ID（可選）
        """
        if message is None:
            message = self._get_localized_message("validation_failed", lang_manager, guild_id, field)
        
        super().__init__(message, "VALIDATION_FAILED")
        self.field = field
    
    def _get_localized_message(self, key: str, lang_manager, guild_id: Optional[str], field: Optional[str] = None) -> str:
        """獲取本地化訊息"""
        if lang_manager and guild_id:
            try:
                base_message = lang_manager.translate(guild_id, "commands", "system_prompt", "errors", key)
                if field:
                    return base_message.format(field=field)
                return base_message
            except Exception:
                pass
        return "驗證失敗"


class ConfigurationError(SystemPromptError):
    """配置錯誤"""
    
    def __init__(self, message: Optional[str] = None, config_path: Optional[str] = None,
                 lang_manager=None, guild_id: Optional[str] = None):
        """
        初始化配置錯誤
        
        Args:
            message: 錯誤訊息（如果為 None，將使用本地化訊息）
            config_path: 配置路徑（可選）
            lang_manager: 語言管理器（可選）
            guild_id: 伺服器 ID（可選）
        """
        if message is None:
            message = self._get_localized_message("configuration_error", lang_manager, guild_id)
        
        super().__init__(message, "CONFIGURATION_ERROR")
        self.config_path = config_path
    
    def _get_localized_message(self, key: str, lang_manager, guild_id: Optional[str]) -> str:
        """獲取本地化訊息"""
        if lang_manager and guild_id:
            try:
                return lang_manager.translate(guild_id, "commands", "system_prompt", "errors", key)
            except Exception:
                pass
        return "配置錯誤"


class ContentTooLongError(ValidationError):
    """內容過長錯誤"""
    
    def __init__(self, max_length: int, current_length: int, lang_manager=None, guild_id=None):
        """
        初始化內容過長錯誤
        
        Args:
            max_length: 最大允許長度
            current_length: 當前內容長度
            lang_manager: 語言管理器（可選）
            guild_id: 伺服器 ID（可選）
        """
        message = f"內容過長（當前 {current_length} 字元，最大 {max_length} 字元）"
        
        if lang_manager and guild_id:
            try:
                message = lang_manager.translate(
                    guild_id,
                    "commands", "system_prompt",
                    "errors", "prompt_too_long"
                ).format(length=current_length, max=max_length)
            except Exception:
                pass  # 使用預設訊息
        
        super().__init__(message, "content")
        self.max_length = max_length
        self.current_length = current_length


class ChannelNotFoundError(SystemPromptError):
    """頻道未找到錯誤"""
    
    def __init__(self, channel_id: str, lang_manager=None, guild_id=None):
        """
        初始化頻道未找到錯誤
        
        Args:
            channel_id: 頻道 ID
            lang_manager: 語言管理器（可選）
            guild_id: 伺服器 ID（可選）
        """
        message = f"找不到頻道 ID: {channel_id}"
        
        if lang_manager and guild_id:
            try:
                message = lang_manager.translate(
                    guild_id,
                    "commands", "system_prompt",
                    "errors", "channel_not_found"
                ).format(channel_id=channel_id)
            except Exception:
                pass  # 使用預設訊息
        
        super().__init__(message, "CHANNEL_NOT_FOUND")
        self.channel_id = channel_id


class PromptNotFoundError(SystemPromptError):
    """系統提示未找到錯誤"""
    
    def __init__(self, scope: str, target_id: str, lang_manager=None, guild_id=None):
        """
        初始化系統提示未找到錯誤
        
        Args:
            scope: 範圍（channel/server）
            target_id: 目標 ID
            lang_manager: 語言管理器（可選）
            guild_id: 伺服器 ID（可選）
        """
        message = f"未找到 {scope} {target_id} 的系統提示"
        
        if lang_manager and guild_id:
            try:
                message = lang_manager.translate(
                    guild_id,
                    "commands", "system_prompt",
                    "errors", "prompt_not_found"
                ).format(scope=scope, target_id=target_id)
            except Exception:
                pass  # 使用預設訊息
        
        super().__init__(message, "PROMPT_NOT_FOUND")
        self.scope = scope
        self.target_id = target_id


class OperationTimeoutError(SystemPromptError):
    """操作超時錯誤"""
    
    def __init__(self, operation: str, timeout_seconds: float, lang_manager=None, guild_id=None):
        """
        初始化操作超時錯誤
        
        Args:
            operation: 操作名稱
            timeout_seconds: 超時秒數
            lang_manager: 語言管理器（可選）
            guild_id: 伺服器 ID（可選）
        """
        message = f"操作 '{operation}' 超時（{timeout_seconds}秒）"
        
        if lang_manager and guild_id:
            try:
                message = lang_manager.translate(
                    guild_id,
                    "commands", "system_prompt",
                    "errors", "timeout"
                ).format(operation=operation, timeout=timeout_seconds)
            except Exception:
                pass  # 使用預設訊息
        
        super().__init__(message, "OPERATION_TIMEOUT")
        self.operation = operation
        self.timeout_seconds = timeout_seconds


class ModuleNotFoundError(SystemPromptError):
    """模組未找到錯誤"""
    
    def __init__(self, module_name: str, lang_manager=None, guild_id=None):
        """
        初始化模組未找到錯誤
        
        Args:
            module_name: 模組名稱
            lang_manager: 語言管理器（可選）
            guild_id: 伺服器 ID（可選）
        """
        message = f"未找到模組: {module_name}"
        
        if lang_manager and guild_id:
            try:
                message = lang_manager.translate(
                    guild_id,
                    "commands", "system_prompt",
                    "errors", "modules_unavailable"
                ).format(module=module_name)
            except Exception:
                pass  # 使用預設訊息
        
        super().__init__(message, "MODULE_NOT_FOUND")
        self.module_name = module_name


class UnsafeContentError(ValidationError):
    """不安全內容錯誤"""
    
    def __init__(self, detected_pattern: str, lang_manager=None, guild_id=None):
        """
        初始化不安全內容錯誤
        
        Args:
            detected_pattern: 檢測到的危險模式
            lang_manager: 語言管理器（可選）
            guild_id: 伺服器 ID（可選）
        """
        message = f"檢測到不安全的內容模式: {detected_pattern}"
        
        if lang_manager and guild_id:
            try:
                message = lang_manager.translate(
                    guild_id,
                    "commands", "system_prompt",
                    "errors", "validation_failed"
                ).format(error=f"檢測到不安全的內容模式: {detected_pattern}")
            except Exception:
                pass  # 使用預設訊息
        
        super().__init__(message, "content")
        self.detected_pattern = detected_pattern