import json
import os
import hashlib
import time
import threading
from typing import Dict, Optional
from addons.logging import get_logger

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Module-level logger
log = get_logger(server_id="Bot", source=__name__)


class ErrorDeduplicator:
    """Tracks recently reported errors to avoid sending duplicates to Discord.
    
    Uses a hash of error type + message + details to identify unique errors.
    Errors within the cooldown period are suppressed.
    
    Attributes:
        _recent_errors: Dict mapping error keys to (timestamp, count).
        _cooldown_seconds: Minimum seconds between reports of the same error.
        _lock: Threading lock for thread-safe operations.
    """
    
    def __init__(self, cooldown_seconds: float = 300.0) -> None:
        """Initialize the error deduplicator.
        
        Args:
            cooldown_seconds: Minimum time between duplicate reports (default 5 min).
        """
        self._recent_errors: Dict[str, tuple[float, int]] = {}
        self._cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._cleanup_threshold = 100  # Clean up when this many entries accumulated
    
    def _make_key(self, error: Exception, details: Optional[str]) -> str:
        """Create a unique key for the error.
        
        Args:
            error: The exception object.
            details: Additional context details.
            
        Returns:
            A hash string identifying this error type + message combination.
        """
        error_type = type(error).__name__
        error_msg = str(error)[:200]  # Truncate long messages
        details_str = (details or "")[:100]
        
        raw_key = f"{error_type}:{error_msg}:{details_str}"
        return hashlib.md5(raw_key.encode()).hexdigest()[:16]
    
    def should_report(self, error: Exception, details: Optional[str] = None) -> bool:
        """Check if this error should be reported or suppressed as duplicate.
        
        Args:
            error: The exception to check.
            details: Additional context for the error.
            
        Returns:
            True if the error should be reported, False if it's a duplicate.
        """
        key = self._make_key(error, details)
        current_time = time.monotonic()
        
        with self._lock:
            # Periodic cleanup of old entries
            if len(self._recent_errors) > self._cleanup_threshold:
                self._cleanup(current_time)
            
            if key in self._recent_errors:
                last_reported, count = self._recent_errors[key]
                
                if current_time - last_reported < self._cooldown_seconds:
                    # Update count but don't report
                    self._recent_errors[key] = (last_reported, count + 1)
                    return False
            
            # Record this error and allow reporting
            self._recent_errors[key] = (current_time, 1)
            return True
    
    def get_suppressed_count(self, error: Exception, details: Optional[str] = None) -> int:
        """Get the number of times this error was suppressed since last report.
        
        Args:
            error: The exception to check.
            details: Additional context for the error.
            
        Returns:
            Number of suppressed duplicates (0 if first occurrence).
        """
        key = self._make_key(error, details)
        with self._lock:
            if key in self._recent_errors:
                _, count = self._recent_errors[key]
                return max(0, count - 1)  # -1 because count includes initial report
            return 0
    
    def _cleanup(self, current_time: float) -> None:
        """Remove expired entries from the cache.
        
        Args:
            current_time: Current monotonic time for expiry comparison.
        """
        expired_keys = [
            k for k, (ts, _) in self._recent_errors.items()
            if current_time - ts > self._cooldown_seconds
        ]
        for k in expired_keys:
            del self._recent_errors[k]


# Global singleton
_error_deduplicator: Optional[ErrorDeduplicator] = None
_dedup_lock = threading.Lock()


def get_error_deduplicator() -> ErrorDeduplicator:
    """Get the global ErrorDeduplicator singleton."""
    global _error_deduplicator
    if _error_deduplicator is None:
        with _dedup_lock:
            if _error_deduplicator is None:
                _error_deduplicator = ErrorDeduplicator(cooldown_seconds=300.0)  # 5 min
    return _error_deduplicator


class Function:
    def __init__(self):
        self.bot = None

    def set_bot(self, bot):
        self.bot = bot

    async def report_error(self, error: Exception, details: str = None):
        """Report an error to Discord with deduplication.
        
        Prevents the same error from being sent multiple times within a cooldown
        period. If an error is suppressed, it will be logged locally but not
        sent to Discord.
        
        Quota/rate limit errors are logged as WARNING instead of ERROR.
        
        Args:
            error: The exception to report.
            details: Additional context about where the error occurred.
        """
        if not self.bot:
            log.error("Function.bot instance is not set; cannot send error report.", action="report_error")
            return
        
        import traceback
        import discord
        
        # Check if this error should be reported or suppressed as duplicate
        deduplicator = get_error_deduplicator()
        
        if not deduplicator.should_report(error, details):
            # Suppressed - log locally but don't send to Discord
            suppressed_count = deduplicator.get_suppressed_count(error, details)
            log.debug(
                f"Suppressed duplicate error report (count: {suppressed_count}): {type(error).__name__}: {str(error)[:100]}",
                action="report_error_suppressed"
            )
            return
        
        # Detect quota/rate limit errors - these should be warnings, not errors
        error_str = str(error).lower()
        is_quota_error = any(kw in error_str for kw in [
            "quota", "resourceexhausted", "429", "rate limit", "ratelimit",
            "exceeded your current quota", "too many requests"
        ])
        
        # Only pass exception parameter if error is actually an Exception object
        if isinstance(error, BaseException):
            if is_quota_error:
                log.warning(message=f"quota/rate limit: {error} details: {details}", exception=error, action="report_warning")
            else:
                log.error(message=f"error: {error} details: {details}", exception=error, action="report_error")
            traceback_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        else:
            # If error is not an Exception (e.g., a string), log without exception parameter
            if is_quota_error:
                log.warning(message=f"quota/rate limit: {error} details: {details}", action="report_warning")
            else:
                log.error(message=f"error: {error} details: {details}", action="report_error")
            traceback_str = f"No traceback available (error is {type(error).__name__}, not Exception)"

        # Use different colors and titles based on error type
        if is_quota_error:
            embed = discord.Embed(
                title="⚠️ 配額警告",
                description=details or "API 配額已達上限，正在使用備用模型。",
                color=discord.Color.yellow()
            )
        else:
            embed = discord.Embed(
                title="錯誤報告",
                description=details or "發生了一個未處理的錯誤。",
                color=discord.Color.red()
            )

        error_field_value = f"```{type(error).__name__}: {error}```"
        if len(error_field_value) > 1024:
            error_field_value = error_field_value[:1021] + "...```"
        embed.add_field(name="錯誤", value=error_field_value, inline=False)

        if len(traceback_str) > 1024:
            traceback_str = traceback_str[:1021] + "..."
        traceback_field_value = f"```python\n{traceback_str}\n```"
        if len(traceback_field_value) > 1024:
            # 重新計算截斷長度
            max_content_len = 1024 - len("```python\n\n```")
            traceback_str = traceback_str[:max_content_len - 3] + "..." if max_content_len > 3 else "..."
            traceback_field_value = f"```python\n{traceback_str}\n```"
        embed.add_field(name="追蹤記錄", value=traceback_field_value, inline=False)
        embed.set_footer(text=f"時間: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        await self.bot.send_error_report(embed)

    def open_json(self, path: str) -> dict:
        try:
            with open(os.path.join(ROOT_DIR, path), encoding="utf8") as json_file:
                return json.load(json_file)
        except:
            return {}

    def update_json(self, path: str, new_data: dict) -> None:
        data = self.open_json(path)
        if not data:
            return
        
        data.update(new_data)

        with open(os.path.join(ROOT_DIR, path), "w") as json_file:
            json.dump(data, json_file, indent=4)

func = Function()