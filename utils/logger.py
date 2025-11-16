"""
logging utilities following technical specifications.

This module provides consistent logging capabilities across all modules,
including structured logging, context tracking, and performance monitoring.
Now integrated with the main logs.py system for unified logging architecture.
"""

import logging
import uuid
import time
import functools
from typing import Optional, Dict, Any, Union
from datetime import datetime, timezone
from contextlib import contextmanager
# Import the structured logging system from logs.py
from logs import setup_enhanced_logger, StructuredRotatingFileHandler


class LoggerMixin:
    """Mixin class providing consistent logging capabilities across modules.
    
    Now integrated with the structured logging system from logs.py for unified architecture.
    
    Features:
    - Automatic correlation ID generation
    - Guild and user context tracking
    - Performance logging decorators
    - Category-based logging
    - Structured logging with extra fields using ENHANCED_FORMAT
    """
    
    def __init__(self, module_name: Optional[str] = None):
        """Initialize LoggerMixin with structured logging system.
        
        Args:
            module_name: Name of the module using this logger
        """
        self._module_name = module_name or self.__class__.__name__
        # Use the structured logger from logs.py system, with fallback for early startup
        try:
            self._logger = setup_enhanced_logger(self._module_name)
        except Exception:
            # Fallback to root logger if structured logger fails (e.g., during early startup)
            self._logger = logging.getLogger(self._module_name)
            self._setup_fallback_handler()
        self._correlation_id = None
        
    def _setup_fallback_handler(self):
        """Setup fallback console handler for early startup logging."""
        # REMOVED: Do not add console handlers to prevent double logging
        # The main.py already sets up the single console handler for all loggers
        # Just configure the logger level and propagation
        
        self._logger.setLevel(logging.INFO)
        
        # Ensure no other handlers interfere with our structured format
        # Set propagate to False to prevent duplicate logging to parent loggers
        self._logger.propagate = True  # Changed to True to use root logger handler
        
    @property
    def logger(self) -> logging.Logger:
        """Get the logger instance for this module."""
        return self._logger
    
    def _generate_correlation_id(self) -> str:
        """Generate a unique correlation ID for request tracing."""
        return str(uuid.uuid4())[:8]
    
    def _get_context_extra(self,
                          category: str = "SYSTEM",
                          guild_id: Optional[str] = None,
                          user_id: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """Get structured logging extra fields with context compatible with logs.py.
        
        Args:
            category: Log category (SYSTEM, USER_ACTION, PERFORMANCE, etc.)
            guild_id: Discord guild/server ID
            user_id: Discord user ID
            **kwargs: Additional structured fields
            
        Returns:
            Dictionary with structured logging fields compatible with logs.py format
        """
        if not self._correlation_id:
            self._correlation_id = self._generate_correlation_id()
        
        # Use field names compatible with logs.py ENHANCED_FORMAT
        extra = {
            "log_category": category,
            "mod_name": self._module_name,
            "custom_module": self._module_name,
            "function_name": self._get_caller_function_name(),
            "correlation_id": self._correlation_id,
            "guild_id": str(guild_id) if guild_id else "N/A",
            "user_id": str(user_id) if user_id else "N/A",
            "duration_ms": kwargs.pop("duration_ms", None),
            "error_code": kwargs.pop("error_code", None)
        }
        
        # Add any remaining kwargs as extra context
        for key, value in kwargs.items():
            if key not in extra:
                extra[key] = value
                
        return extra
    
    def _get_caller_function_name(self) -> str:
        """Get the name of the calling function for structured logging."""
        import inspect
        frame = None
        try:
            frame = inspect.currentframe()
            if frame and frame.f_back and frame.f_back.f_back:
                frame = frame.f_back.f_back
                if frame and frame.f_code:
                    return frame.f_code.co_name
        except Exception:
            pass
        finally:
            if frame:
                try:
                    del frame
                except:
                    pass
        return "unknown"
    
    def log_with_context(self,
                        level: int,
                        message: str,
                        category: str = "SYSTEM",
                        guild_id: Optional[str] = None,
                        user_id: Optional[str] = None,
                        **kwargs):
        """Log message with structured context compatible with logs.py system.
        
        Args:
            level: Logging level (logging.DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Log message
            category: Log category for filtering
            guild_id: Discord guild/server ID
            user_id: Discord user ID
            **kwargs: Additional structured fields compatible with logs.py
        """
        extra = self._get_context_extra(category, guild_id, user_id, **kwargs)
        
        # Ensure extra fields are compatible with logs.py ENHANCED_FORMAT
        self._logger.log(level, message, extra=extra)
    
    def debug(self, message: str, category: str = "DEBUG", guild_id: Optional[str] = None,
              user_id: Optional[str] = None, **kwargs):
        """Log debug message with context."""
        self.log_with_context(logging.DEBUG, message, category, guild_id, user_id, **kwargs)
    
    def info(self, message: str, category: str = "SYSTEM", guild_id: Optional[str] = None,
             user_id: Optional[str] = None, **kwargs):
        """Log info message with context."""
        self.log_with_context(logging.INFO, message, category, guild_id, user_id, **kwargs)
    
    def warning(self, message: str, category: str = "SYSTEM", guild_id: Optional[str] = None,
                user_id: Optional[str] = None, **kwargs):
        """Log warning message with context."""
        self.log_with_context(logging.WARNING, message, category, guild_id, user_id, **kwargs)
    
    def error(self, message: str, category: str = "ERROR", guild_id: Optional[str] = None,
              user_id: Optional[str] = None, exc_info: Optional[Exception] = None, **kwargs):
        """Log error message with context and optional exception info."""
        extra = self._get_context_extra(category, guild_id, user_id, **kwargs)
        
        if exc_info:
            self._logger.error(message, extra=extra, exc_info=exc_info)
        else:
            self._logger.error(message, extra=extra)
    
    def critical(self, message: str, category: str = "CRITICAL", guild_id: Optional[str] = None,
                 user_id: Optional[str] = None, exc_info: Optional[Exception] = None, **kwargs):
        """Log critical message with context and optional exception info."""
        extra = self._get_context_extra(category, guild_id, user_id, **kwargs)
        
        if exc_info:
            self._logger.critical(message, extra=extra, exc_info=exc_info)
        else:
            self._logger.critical(message, extra=extra)
    
    def set_correlation_id(self, correlation_id: str):
        """Set a specific correlation ID for request tracing."""
        self._correlation_id = correlation_id
    
    def clear_correlation_id(self):
        """Clear the current correlation ID."""
        self._correlation_id = None


def performance_logger(module_name: Optional[str] = None):
    """Decorator for logging function performance metrics.
    
    Args:
        module_name: Name of the module for logging context
        
    Returns:
        Decorated function with performance logging
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            correlation_id = str(uuid.uuid4())[:8]
            
            logger = logging.getLogger(module_name or func.__module__)
            logger.info(
                f"Starting {func.__name__}",
                extra={
                    "category": "PERFORMANCE",
                    "mod_name": module_name or func.__module__,
                    "function": func.__name__,
                    "correlation_id": correlation_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                logger.info(
                    f"Completed {func.__name__} successfully",
                    extra={
                        "category": "PERFORMANCE",
                        "mod_name": module_name or func.__module__,
                        "function": func.__name__,
                        "correlation_id": correlation_id,
                        "duration_ms": round(duration * 1000, 2),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"Failed {func.__name__}: {e}",
                    extra={
                        "category": "PERFORMANCE",
                        "mod_name": module_name or func.__module__,
                        "function": func.__name__,
                        "correlation_id": correlation_id,
                        "duration_ms": round(duration * 1000, 2),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    },
                    exc_info=e
                )
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            correlation_id = str(uuid.uuid4())[:8]
            
            logger = logging.getLogger(module_name or func.__module__)
            logger.info(
                f"Starting {func.__name__}",
                extra={
                    "category": "PERFORMANCE",
                    "mod_name": module_name or func.__module__,
                    "function": func.__name__,
                    "correlation_id": correlation_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                logger.info(
                    f"Completed {func.__name__} successfully",
                    extra={
                        "category": "PERFORMANCE",
                        "mod_name": module_name or func.__module__,
                        "function": func.__name__,
                        "correlation_id": correlation_id,
                        "duration_ms": round(duration * 1000, 2),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"Failed {func.__name__}: {e}",
                    extra={
                        "category": "PERFORMANCE",
                        "mod_name": module_name or func.__module__,
                        "function": func.__name__,
                        "correlation_id": correlation_id,
                        "duration_ms": round(duration * 1000, 2),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    },
                    exc_info=e
                )
                raise
        
        # Return appropriate wrapper based on function type
        if hasattr(func, '__call__'):
            if hasattr(func, '__code__') and 'async def' in func.__code__.co_filename:
                return async_wrapper
            else:
                return sync_wrapper
        return func
    
    return decorator


@contextmanager
def logging_context(category: str = "SYSTEM",
                   guild_id: Optional[str] = None,
                   user_id: Optional[str] = None,
                   module_name: Optional[str] = None,
                   **kwargs):
    """Context manager for structured logging with context.
    
    Args:
        category: Log category
        guild_id: Discord guild/server ID
        user_id: Discord user ID
        module_name: Module name for logging
        **kwargs: Additional structured fields
    """
    correlation_id = str(uuid.uuid4())[:8]
    logger = logging.getLogger(module_name or "context")
    
    logger.info(
        f"Entering logging context: {category}",
        extra={
            "category": category,
            "mod_name": module_name or "context",
            "correlation_id": correlation_id,
            "guild_id": guild_id,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs
        }
    )
    
    try:
        yield correlation_id
    finally:
        logger.info(
            f"Exiting logging context: {category}",
            extra={
                "category": category,
                "mod_name": module_name or "context",
                "correlation_id": correlation_id,
                "guild_id": guild_id,
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **kwargs
            }
        )


class StructuredLogger:
    """Utility class for creating structured log messages."""
    
    @staticmethod
    def create_log_entry(level: str,
                        category: str,
                        message: str,
                        module: str,
                        function: Optional[str] = None,
                        line: Optional[int] = None,
                        guild_id: Optional[str] = None,
                        user_id: Optional[str] = None,
                        correlation_id: Optional[str] = None,
                        duration_ms: Optional[float] = None,
                        error_code: Optional[str] = None,
                        **extra_fields) -> Dict[str, Any]:
        """Create a structured log entry following technical specifications.
        
        Format: [TIMESTAMP] [LEVEL] [CATEGORY] [MODULE] [FUNCTION] [LINE] [GUILD:id] [USER:id] MESSAGE
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            category: Log category (SYSTEM, USER_ACTION, PERFORMANCE, etc.)
            message: Log message
            module: Module name
            function: Function name (optional)
            line: Line number (optional)
            guild_id: Discord guild ID (optional)
            user_id: Discord user ID (optional)
            correlation_id: Request correlation ID (optional)
            duration_ms: Execution duration in milliseconds (optional)
            error_code: Structured error code (optional)
            **extra_fields: Additional fields to include
            
        Returns:
            Dictionary with structured log entry
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        log_entry: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": level.upper(),
            "category": category.upper(),
            "mod_name": module,
            "message": message
        }
        
        if function:
            log_entry["function"] = function
        if line:
            log_entry["line"] = str(line)
        if guild_id:
            log_entry["guild_id"] = str(guild_id)
        if user_id:
            log_entry["user_id"] = str(user_id)
        if correlation_id:
            log_entry["correlation_id"] = correlation_id
        if duration_ms:
            log_entry["duration_ms"] = duration_ms
        if error_code:
            log_entry["error_code"] = error_code
            
        log_entry.update(extra_fields)
        return log_entry
    
    @staticmethod
    def format_log_message(log_entry: Dict[str, Any]) -> str:
        """Format structured log entry as readable message.
        
        Args:
            log_entry: Structured log entry dictionary
            
        Returns:
            Formatted log message string
        """
        parts = [
            f"[{log_entry.get('timestamp', '')}]",
            f"[{log_entry.get('level', '')}]",
            f"[{log_entry.get('category', '')}]",
            f"[{log_entry.get('module', '')}]"
        ]
        
        if "function" in log_entry:
            parts.append(f"[{log_entry['function']}]")
        if "line" in log_entry:
            parts.append(f"[{log_entry['line']}]")
        if "guild_id" in log_entry:
            parts.append(f"[GUILD:{log_entry['guild_id']}]")
        if "user_id" in log_entry:
            parts.append(f"[USER:{log_entry['user_id']}]")
            
        message = " ".join(parts) + f" {log_entry.get('message', '')}"
        
        # Add additional fields if present
        additional_fields = []
        for key, value in log_entry.items():
            if key not in ["timestamp", "level", "category", "module", "function",
                          "line", "guild_id", "user_id", "message"]:
                additional_fields.append(f"{key}={value}")
        
        if additional_fields:
            message += f" | {' '.join(additional_fields)}"
            
        return message


# Convenience functions for common logging patterns
def log_user_action(message: str, module: str, guild_id: Optional[str] = None, user_id: Optional[str] = None, **kwargs):
    """Log user action with structured context."""
    logger = logging.getLogger(module)
    log_entry = StructuredLogger.create_log_entry(
        level="INFO",
        category="USER_ACTION",
        message=message,
        module=module,
        guild_id=guild_id,
        user_id=user_id,
        **kwargs
    )
    logger.info(StructuredLogger.format_log_message(log_entry), extra=log_entry)


def log_system_event(message: str, module: str, category: str = "SYSTEM", **kwargs):
    """Log system event with structured context."""
    logger = logging.getLogger(module)
    log_entry = StructuredLogger.create_log_entry(
        level="INFO",
        category=category,
        message=message,
        module=module,
        **kwargs
    )
    logger.info(StructuredLogger.format_log_message(log_entry), extra=log_entry)


def log_performance_metric(operation: str,
                          module: str,
                          duration_ms: float,
                          guild_id: Optional[str] = None,
                          user_id: Optional[str] = None,
                          **kwargs):
    """Log performance metric with structured context."""
    logger = logging.getLogger(module)
    log_entry = StructuredLogger.create_log_entry(
        level="INFO",
        category="PERFORMANCE",
        message=f"Operation completed: {operation}",
        module=module,
        duration_ms=duration_ms,
        guild_id=guild_id,
        user_id=user_id,
        **kwargs
    )
    logger.info(StructuredLogger.format_log_message(log_entry), extra=log_entry)


def log_error(error: Exception,
             message: str,
             module: str,
             category: str = "ERROR",
             guild_id: Optional[str] = None,
             user_id: Optional[str] = None,
             error_code: Optional[str] = None,
             **kwargs):
    """Log error with structured context and exception info."""
    logger = logging.getLogger(module)
    log_entry = StructuredLogger.create_log_entry(
        level="ERROR",
        category=category,
        message=message,
        module=module,
        guild_id=guild_id,
        user_id=user_id,
        error_code=error_code,
        **kwargs
    )
    logger.error(StructuredLogger.format_log_message(log_entry), extra=log_entry, exc_info=error)