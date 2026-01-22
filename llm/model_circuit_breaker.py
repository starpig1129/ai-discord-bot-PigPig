"""ModelCircuitBreaker: Tracks model failures and temporarily skips known-failing models.

This module implements a circuit breaker pattern to prevent repeated API calls
to models that are known to fail (due to quota exhaustion, non-existent models,
rate limits, etc.). Failed models are temporarily marked as 'open' (unavailable)
and will be skipped until a cooldown period expires.

Typical usage:
    from llm.model_circuit_breaker import get_model_circuit_breaker
    
    cb = get_model_circuit_breaker()
    
    # Check before calling
    if cb.is_available(model_name):
        try:
            result = await call_model(model_name)
        except Exception as e:
            cb.record_failure(model_name, e)
"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Optional, Type

from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="llm.model_circuit_breaker")


class ErrorCategory(Enum):
    """Categorizes errors for different cooldown strategies."""
    
    QUOTA_EXHAUSTED = auto()     # 429 / ResourceExhausted - long cooldown
    MODEL_NOT_FOUND = auto()     # 404 / NotFound - very long cooldown
    RATE_LIMITED = auto()        # 429 but transient - short cooldown
    AUTHENTICATION = auto()      # 401 / 403 - permanent until restart
    TRANSIENT = auto()           # Temporary network issues - short cooldown
    UNKNOWN = auto()             # Catch-all - moderate cooldown


# Cooldown durations in seconds for each error category
COOLDOWN_SECONDS: Dict[ErrorCategory, float] = {
    ErrorCategory.QUOTA_EXHAUSTED: 120.0,   # 2 minutes for quota
    ErrorCategory.MODEL_NOT_FOUND: 3600.0,  # 1 hour for non-existent models
    ErrorCategory.RATE_LIMITED: 30.0,       # 30 seconds for rate limits
    ErrorCategory.AUTHENTICATION: 7200.0,   # 2 hours for auth issues
    ErrorCategory.TRANSIENT: 10.0,          # 10 seconds for transient issues
    ErrorCategory.UNKNOWN: 60.0,            # 1 minute for unknown errors
}


@dataclass
class FailureRecord:
    """Record of a model failure."""
    
    model_name: str
    category: ErrorCategory
    failure_time: float
    cooldown_until: float
    error_message: str
    consecutive_failures: int = 1


class ModelCircuitBreaker:
    """Thread-safe circuit breaker for LLM model calls.
    
    Tracks model failures and temporarily disables calls to models that are
    known to be failing. This prevents wasting API quota and reduces latency
    by avoiding doomed retry attempts.
    
    Attributes:
        _failures: Dict mapping model names to their failure records.
        _lock: Threading lock for thread-safe operations.
    """
    
    def __init__(self) -> None:
        """Initialize the circuit breaker with empty failure tracking."""
        self._failures: Dict[str, FailureRecord] = {}
        self._lock = threading.Lock()
    
    def categorize_error(self, error: Exception) -> ErrorCategory:
        """Classify an exception into an error category.
        
        Args:
            error: The exception to categorize.
            
        Returns:
            The ErrorCategory that best matches the exception.
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # Check for quota/rate limit errors
        if any(kw in error_str for kw in ["quota", "resourceexhausted", "429"]):
            # Distinguish between daily quota and transient rate limits
            if "daily" in error_str or "per day" in error_str.replace(" ", ""):
                return ErrorCategory.QUOTA_EXHAUSTED
            return ErrorCategory.RATE_LIMITED
        
        # Check for model not found errors
        if any(kw in error_str for kw in ["not found", "notfound", "404", "does not exist"]):
            return ErrorCategory.MODEL_NOT_FOUND
        
        # Check for authentication errors
        if any(kw in error_str for kw in ["unauthorized", "forbidden", "401", "403", "api key"]):
            return ErrorCategory.AUTHENTICATION
        
        # Check for transient network errors
        if any(kw in error_type for kw in ["timeout", "connection", "network"]):
            return ErrorCategory.TRANSIENT
        
        return ErrorCategory.UNKNOWN
    
    def is_available(self, model_name: str) -> bool:
        """Check if a model is currently available (not in cooldown).
        
        Args:
            model_name: The model identifier (e.g., 'google_genai:gemini-2.5-flash').
            
        Returns:
            True if the model can be tried, False if it's in cooldown.
        """
        with self._lock:
            if model_name not in self._failures:
                return True
            
            record = self._failures[model_name]
            current_time = time.monotonic()
            
            if current_time >= record.cooldown_until:
                # Cooldown expired, remove record and allow retry
                logger.info(
                    f"Circuit breaker reset for model '{model_name}' "
                    f"(was {record.category.name})"
                )
                del self._failures[model_name]
                return True
            
            remaining = record.cooldown_until - current_time
            logger.debug(
                f"Model '{model_name}' in cooldown for {remaining:.1f}s more "
                f"(category: {record.category.name})"
            )
            return False
    
    def record_failure(
        self,
        model_name: str,
        error: Exception,
        category: Optional[ErrorCategory] = None
    ) -> None:
        """Record a model failure and start the cooldown period.
        
        Args:
            model_name: The model identifier that failed.
            error: The exception that occurred.
            category: Optional explicit category (auto-detected if not provided).
        """
        with self._lock:
            if category is None:
                category = self.categorize_error(error)
            
            cooldown_duration = COOLDOWN_SECONDS.get(category, 60.0)
            current_time = time.monotonic()
            
            # Check for existing failure and increment consecutive count
            consecutive = 1
            if model_name in self._failures:
                old_record = self._failures[model_name]
                consecutive = old_record.consecutive_failures + 1
                # Increase cooldown for repeated failures (exponential backoff)
                cooldown_duration *= min(consecutive, 4)  # Cap at 4x
            
            cooldown_until = current_time + cooldown_duration
            
            self._failures[model_name] = FailureRecord(
                model_name=model_name,
                category=category,
                failure_time=current_time,
                cooldown_until=cooldown_until,
                error_message=str(error)[:200],  # Truncate long messages
                consecutive_failures=consecutive,
            )
            
            logger.warning(
                f"Circuit breaker activated for '{model_name}': "
                f"category={category.name}, cooldown={cooldown_duration:.0f}s, "
                f"failures={consecutive}"
            )
    
    def get_available_models(self, model_list: list[str]) -> list[str]:
        """Filter a model list to only include available models.
        
        Args:
            model_list: List of model identifiers to filter.
            
        Returns:
            List of models that are currently available (not in cooldown).
        """
        return [m for m in model_list if self.is_available(m)]
    
    def reset(self, model_name: Optional[str] = None) -> None:
        """Reset circuit breaker state.
        
        Args:
            model_name: Specific model to reset, or None to reset all.
        """
        with self._lock:
            if model_name is None:
                self._failures.clear()
                logger.info("Circuit breaker reset for all models")
            elif model_name in self._failures:
                del self._failures[model_name]
                logger.info(f"Circuit breaker reset for model '{model_name}'")
    
    def get_status(self) -> Dict[str, Dict]:
        """Get current status of all tracked failures.
        
        Returns:
            Dict mapping model names to their failure status info.
        """
        with self._lock:
            current_time = time.monotonic()
            return {
                name: {
                    "category": record.category.name,
                    "remaining_cooldown": max(0, record.cooldown_until - current_time),
                    "consecutive_failures": record.consecutive_failures,
                    "error_preview": record.error_message[:100],
                }
                for name, record in self._failures.items()
            }


# Singleton instance
_circuit_breaker: Optional[ModelCircuitBreaker] = None
_cb_lock = threading.Lock()


def get_model_circuit_breaker() -> ModelCircuitBreaker:
    """Get the global ModelCircuitBreaker singleton instance.
    
    Returns:
        The singleton ModelCircuitBreaker instance.
    """
    global _circuit_breaker
    if _circuit_breaker is None:
        with _cb_lock:
            if _circuit_breaker is None:
                _circuit_breaker = ModelCircuitBreaker()
    return _circuit_breaker


__all__ = [
    "ModelCircuitBreaker",
    "get_model_circuit_breaker",
    "ErrorCategory",
    "COOLDOWN_SECONDS",
]
