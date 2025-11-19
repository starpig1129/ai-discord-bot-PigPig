# addons/logging_manager.py
# Core logging manager implementing structured NDJSON sinks and console rendering.

import json
import os
import threading
import time
import traceback
import logging
import sys
import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from queue import Empty, Full, Queue
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger as loguru_logger

from addons import settings

# Try importing project error reporting helper. Report failures via fallback print.
try:
    from function import func
except Exception:  # pragma: no cover - defensive fallback
    func = None

# Placeholder for logging configuration; real values are loaded from addons.settings.BaseConfig
_LOG_CFG: Dict[str, Any] = {}

# Minimal internal defaults — prefer user-provided settings from addons.settings.BaseConfig.
# Keep these minimal to avoid duplicating the full default schema defined in BaseConfig.
_MINIMAL_DEFAULTS = {
    "console": {"enabled": True, "color": True, "level": "INFO"},
    "color_map": {
        "level": {"ERROR": "red", "WARNING": "yellow", "INFO": "green", "DEBUG": "cyan", "CRITICAL": "bright_red"},
        "source": {"system": "magenta", "external": "blue", "server": "bright_blue"},
        "fields": {
            "timestamp": "bright_black",
            "channel": "bright_black",
            "user": "bright_black",
            "action": "bright_cyan",
            "message": "white",
        },
    },
    "async": {"batch_size": 500, "flush_interval": 2.0},
    "log_base_path": "logs",
    "use_emoji": False,
}
# Initialize CONFIG with minimal defaults; real configuration is loaded later by load_config_from_settings()
CONFIG: Dict[str, Any] = dict(_MINIMAL_DEFAULTS)
# Ensure nested keys exist for safe access before load_config_from_settings is called.
CONFIG.setdefault("console", {}).setdefault("enabled", True)
CONFIG.setdefault("console", {}).setdefault("color", True)
CONFIG.setdefault("console", {}).setdefault("level", "INFO")
CONFIG.setdefault("color_map", {}).setdefault("fields", {})
CONFIG.setdefault("async", {})


def _check_color_support() -> bool:
    """Enhanced check for terminal color support including Windows."""
    # Check if stderr is a TTY
    if not sys.stderr.isatty():
        return False
    
    # Check TERM environment variable
    term = os.environ.get("TERM", "")
    if term in ("dumb", ""):
        return False
    
    # Check for NO_COLOR environment variable (standard)
    if os.environ.get("NO_COLOR"):
        return False
    
    # Check for FORCE_COLOR
    if os.environ.get("FORCE_COLOR"):
        return True
    
    # Windows specific check
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Enable ANSI escape sequences on Windows 10+
            # STD_OUTPUT_HANDLE = -11, ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            mode.value |= 0x0004
            kernel32.SetConsoleMode(handle, mode)
            
            # Also enable for stderr
            handle_err = kernel32.GetStdHandle(-12)
            mode_err = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle_err, ctypes.byref(mode_err))
            mode_err.value |= 0x0004
            kernel32.SetConsoleMode(handle_err, mode_err)
            return True
        except Exception:
            # If Windows ANSI setup fails, disable colors
            return False
    
    return True


# Previously we attempted to read settings at import time which caused a race
# with addons.settings (circular import). Instead, provide explicit functions
# that load the logging config from addons.settings.base_config and initialize
# the loguru console sink. addons.settings will call these after it instantiates
# BaseConfig so CONFIG_ROOT is respected and user-provided defaults are applied.
_LOG_CFG = _LOG_CFG or {}

# Runtime flags (populated by load_config_from_settings)
CONSOLE_SUPPORTS_ANSI = False
CONSOLE_COLOR_ENABLED = False

def load_config_from_settings() -> None:
    """Load logging configuration from addons.settings.base_config and merge with defaults.

    This function should be called by addons.settings after it successfully
    constructs BaseConfig from CONFIG_ROOT so user configuration is applied.
    """
    global _LOG_CFG, CONFIG, CONSOLE_SUPPORTS_ANSI, CONSOLE_COLOR_ENABLED
    try:
        base_cfg = getattr(settings, "base_config", None)
        if isinstance(base_cfg, dict):
            _LOG_CFG = base_cfg.get("logging", {}) or {}
        elif base_cfg is not None:
            try:
                _LOG_CFG = getattr(base_cfg, "logging", {}) or {}
            except Exception:
                _LOG_CFG = {}
        else:
            _LOG_CFG = {}
    except Exception:
        _LOG_CFG = {}

    # Merge minimal defaults with provided config (shallow merge)
    CONFIG = {**_MINIMAL_DEFAULTS, **_LOG_CFG} if "_MINIMAL_DEFAULTS" in globals() else {**_LOG_CFG}
    CONFIG["console"] = {**_MINIMAL_DEFAULTS.get("console", {}), **CONFIG.get("console", {})}
    CONFIG["color_map"] = {**_MINIMAL_DEFAULTS.get("color_map", {}), **CONFIG.get("color_map", {})}
    CONFIG["color_map"]["fields"] = {
        **_MINIMAL_DEFAULTS.get("color_map", {}).get("fields", {}),
        **CONFIG.get("color_map", {}).get("fields", {}),
    }
    CONFIG["async"] = {**_MINIMAL_DEFAULTS.get("async", {}), **CONFIG.get("async", {})}
    # Ensure use_emoji respects user config in LOG_CFG, otherwise fall back to minimal default
    CONFIG["use_emoji"] = _LOG_CFG.get("use_emoji", _MINIMAL_DEFAULTS.get("use_emoji", False))

    # Update color support flags
    _console_supports_ansi = _check_color_support()
    CONSOLE_SUPPORTS_ANSI = _console_supports_ansi
    CONSOLE_COLOR_ENABLED = bool(CONFIG.get("console", {}).get("color", True)) and _console_supports_ansi

def init_loguru_console() -> None:
    """Initialize or reconfigure the loguru console sink based on current CONFIG.

    Call this after load_config_from_settings() so the console format and color
    options come from the user's configuration.
    """
    try:
        # Remove existing handlers to avoid duplicate output.
        loguru_logger.remove()
        # Load console preferences from CONFIG
        console_level = CONFIG.get("console", {}).get("level", "INFO")
        console_color = bool(CONFIG.get("console", {}).get("color", True))
        # Format string may be provided by config; fall back to minimal message-only format.
        console_format = CONFIG.get("console", {}).get("format", "{message}")
        colorize = bool(console_color) and CONSOLE_SUPPORTS_ANSI
        loguru_logger.add(
            sys.stderr,
            format=console_format,
            colorize=colorize,
            level=str(console_level).upper(),
        )
    except Exception:
        # If configuring loguru fails, report and continue without raising.
        if func:
            try:
                asyncio.create_task(func.report_error(Exception("loguru init failed"), "addons/logging.py/init_loguru_console"))
            except Exception:
                print("loguru init failed")
        else:
            print("loguru init failed")


@dataclass
class LogRecord:
    """Structured log record following plan.md schema."""

    timestamp: str
    level: str
    source: str
    server_id: str
    channel_or_file: str = ""
    user_id: str = ""
    action: str = ""
    message: str = ""
    trace_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_json_line(self) -> str:
        """Serialize record to a single NDJSON line."""
        obj = {
            "timestamp": self.timestamp,
            "level": self.level,
            "source": self.source,
            "server_id": self.server_id,
            "channel_or_file": self.channel_or_file,
            "user_id": self.user_id,
            "action": self.action,
            "message": self.message,
            "trace_id": self.trace_id,
            "extra": self.extra or {},
        }
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class BackgroundWriter:
    """Background single-thread writer that batches NDJSON records and writes per-level files."""

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        async_cfg = CONFIG.get("async", {})
        self.batch_size: int = int(async_cfg.get("batch_size", 500))
        self.flush_interval: float = float(async_cfg.get("flush_interval", 2.0))
        self.queue_maxsize: int = max(8, self.batch_size * 4)
        self._queue: "Queue[Dict[str, Any]]" = Queue(maxsize=self.queue_maxsize)
        self._thread = threading.Thread(target=self._worker, name="logging-writer", daemon=True)
        self._stop_event = threading.Event()
        self._metrics = {"emitted": 0, "dropped": 0}
        self._thread.start()

    @classmethod
    def get_instance(cls) -> "BackgroundWriter":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = BackgroundWriter()
            return cls._instance

    def enqueue(self, server_id: str, level: str, json_line: str, timestamp_iso: str) -> None:
        """Attempt to enqueue a log event non-blocking. On full queue, drop and report."""
        item = {"server_id": str(server_id), "level": level, "json_line": json_line, "timestamp": timestamp_iso}
        try:
            self._queue.put_nowait(item)
            self._metrics["emitted"] += 1
        except Full:
            # Drop the record and report asynchronously
            self._metrics["dropped"] += 1
            err = Exception(f"Logging queue full (maxsize={self.queue_maxsize}). Dropping log for server_id={server_id}")
            self._report_error_async(err, "addons/logging_manager.py/enqueue")

    def _report_error_async(self, exc: Exception, context: str) -> None:
        """Report errors through func.report_error if available, fallback to printing."""
        try:
            if func:
                try:
                    asyncio.create_task(func.report_error(exc, context))
                    return
                except Exception:
                    # If scheduling failed, fallthrough to sync call below.
                    pass
            # Fallback synchronous print
            print(f"[logging_manager.report_error] {context}: {exc}")
        except Exception:
            print("Failed to report error from logging manager:", traceback.format_exc())

    def stop(self, timeout: float = 5.0) -> None:
        """Signal worker to stop and flush remaining items."""
        self._stop_event.set()
        self._thread.join(timeout=timeout)

    def _worker(self) -> None:
        """Worker loop: collect batches and perform grouped writes per server/date/level."""
        # Retry policy
        max_retries = 3
        retry_backoff = 0.2
        while not self._stop_event.is_set():
            batch: List[Dict[str, Any]] = []
            start = time.time()
            # Block up to flush_interval to collect at least one item
            try:
                first = self._queue.get(timeout=self.flush_interval)
                batch.append(first)
            except Empty:
                # Timeout: nothing to flush
                continue

            # Drain additional items up to batch_size - 1 without blocking
            while len(batch) < self.batch_size:
                try:
                    item = self._queue.get_nowait()
                    batch.append(item)
                except Empty:
                    break

            # Group by server_id + date + level to minimize file writes
            grouped: Dict[str, List[str]] = {}
            for it in batch:
                try:
                    ts = it.get("timestamp")
                    # parse date from ISO timestamp robustly
                    if isinstance(ts, str):
                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            date_str = dt.strftime("%Y%m%d")
                        except Exception:
                            date_str = datetime.utcnow().strftime("%Y%m%d")
                    else:
                        date_str = datetime.utcnow().strftime("%Y%m%d")
                    server = str(it.get("server_id", "unknown"))
                    level = it.get("level", "INFO")
                    key = f"{server}|{date_str}|{level}"
                    grouped.setdefault(key, []).append(it.get("json_line", ""))
                except Exception:
                    # Should not fail; report and continue
                    self._report_error_async(Exception("Failed to bucket log item"), "_worker/bucketing")

            # Write each group into its file in a robust manner
            for key, lines in grouped.items():
                server, date_str, level = key.split("|", 2)
                log_dir = os.path.join(CONFIG.get("log_base_path", "logs"), server, date_str)
                os.makedirs(log_dir, exist_ok=True)
                filename = os.path.join(log_dir, f"{level.lower()}.jsonl")
                attempt = 0
                written = False
                last_exc: Optional[Exception] = None
                while attempt < max_retries and not written:
                    try:
                        # Write all lines in one open/append operation to reduce syscalls
                        with open(filename, "a", encoding="utf-8") as fh:
                            fh.write("\n".join(lines))
                            fh.write("\n")
                            fh.flush()
                            if CONFIG.get("fsync_on_flush", False):
                                try:
                                    os.fsync(fh.fileno())
                                except Exception:
                                    # fsync best-effort; do not fail whole write if unsupported
                                    pass
                        written = True
                    except Exception as e:
                        last_exc = e
                        attempt += 1
                        time.sleep(retry_backoff * attempt)
                if not written:
                    # On persistent failure write emergency stash and report
                    try:
                        emergency_dir = os.path.join(CONFIG.get("log_base_path", "logs"), "emergency")
                        os.makedirs(emergency_dir, exist_ok=True)
                        tsnow = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                        emergency_file = os.path.join(emergency_dir, f"emergency_{server}_{tsnow}.jsonl")
                        with open(emergency_file, "a", encoding="utf-8") as ef:
                            ef.write("\n".join(lines))
                            ef.write("\n")
                    except Exception as e2:
                        # If even emergency write fails, report both errors
                        combined = Exception(f"Failed to write logs and emergency stash: {last_exc} ; {e2}")
                        self._report_error_async(combined, "addons/logging_manager.py/_worker")
                    else:
                        self._report_error_async(last_exc or Exception("Unknown write error"), "addons/logging_manager.py/_worker")

        # Drain remaining items on exit
        remaining: List[Dict[str, Any]] = []
        while True:
            try:
                remaining.append(self._queue.get_nowait())
            except Empty:
                break
        if remaining:
            # Attempt a final flush (best-effort)
            grouped_final: Dict[str, List[str]] = {}
            for it in remaining:
                ts = it.get("timestamp")
                if isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        date_str = dt.strftime("%Y%m%d")
                    except Exception:
                        date_str = datetime.utcnow().strftime("%Y%m%d")
                else:
                    date_str = datetime.utcnow().strftime("%Y%m%d")
                server = str(it.get("server_id", "unknown"))
                level = it.get("level", "INFO")
                key = f"{server}|{date_str}|{level}"
                grouped_final.setdefault(key, []).append(it.get("json_line", ""))
            for key, lines in grouped_final.items():
                server, date_str, level = key.split("|", 2)
                log_dir = os.path.join(CONFIG.get("log_base_path", "logs"), server, date_str)
                os.makedirs(log_dir, exist_ok=True)
                filename = os.path.join(log_dir, f"{level.lower()}.jsonl")
                try:
                    with open(filename, "a", encoding="utf-8") as fh:
                        fh.write("\n".join(lines))
                        fh.write("\n")
                        fh.flush()
                except Exception as e:
                    self._report_error_async(e, "addons/logging_manager.py/final_flush")


class LoggerAdapter:
    """Logger-like object exposing bind(...) and level methods (info/warning/error/debug).

    This provides a minimal structlog-like API for bindable context while delegating
    actual output to BackgroundWriter and loguru console renderer.
    """

    # ANSI color codes mapping
    _COLORS = {
        "black": "\x1b[30m",
        "red": "\x1b[31m",
        "green": "\x1b[32m",
        "yellow": "\x1b[33m",
        "blue": "\x1b[34m",
        "magenta": "\x1b[35m",
        "cyan": "\x1b[36m",
        "white": "\x1b[37m",
        "bright_black": "\x1b[90m",
        "bright_red": "\x1b[91m",
        "bright_green": "\x1b[92m",
        "bright_yellow": "\x1b[93m",
        "bright_blue": "\x1b[94m",
        "bright_magenta": "\x1b[95m",
        "bright_cyan": "\x1b[96m",
        "bright_white": "\x1b[97m",
        "bold": "\x1b[1m",
        "dim": "\x1b[2m",
        "reset": "\x1b[0m",
    }

    # Emoji mapping for levels
    _LEVEL_EMOJI = {
        "DEBUG": "🔍",
        "INFO": "✅",
        "WARNING": "⚠️ ",
        "ERROR": "❌",
        "CRITICAL": "🚨"
    }

    def __init__(
        self,
        server_id: str,
        source: str = "server",
        channel: Optional[str] = None,
        bound: Optional[Dict[str, Any]] = None,
    ):
        self.server_id = str(server_id)
        self.source = source
        self.channel = channel or ""
        self.bound_context: Dict[str, Any] = dict(bound or {})
        self._writer = BackgroundWriter.get_instance()

    def bind(self, **context: Any) -> "LoggerAdapter":
        """Return a new LoggerAdapter with merged context, similar to structlog.bind."""
        merged = {**self.bound_context, **context}
        return LoggerAdapter(self.server_id, source=self.source, channel=self.channel, bound=merged)

    def _emit(self, level: str, message: str, exception: Optional[BaseException], **event_fields: Any) -> None:
        """Compose structured record, enqueue NDJSON line, and render to console as single-line text."""
        # Compose timestamp in ISO 8601 UTC
        timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        # Merge contexts: bound_context < event_fields (event_fields override bound)
        merged = {**self.bound_context, **(event_fields or {})}
        # Extract standard fields
        channel_or_file = merged.pop("channel_or_file", None) or merged.pop("channel", None) or self.channel or ""
        user_id = str(merged.pop("user_id", merged.pop("user", ""))) if merged.get("user_id") or merged.get("user") else merged.pop("user_id", "")
        action = merged.pop("action", "")
        trace_id = merged.pop("trace_id", None)
        # Message: prefer passed message parameter, but allow 'message' in event_fields to override
        msg_field = merged.pop("message", None)
        full_message = msg_field if msg_field is not None else (message or "")
        # Remaining merged keys become 'extra'
        extra = merged or {}

        record = LogRecord(
            timestamp=timestamp,
            level=level.upper(),
            source=self.source,
            server_id=self.server_id,
            channel_or_file=str(channel_or_file),
            user_id=str(user_id) if user_id is not None else "",
            action=str(action),
            message=str(full_message),
            trace_id=str(trace_id) if trace_id is not None else None,
            extra=extra,
        )
        json_line = record.to_json_line()
        # Enqueue for background file write
        try:
            self._writer.enqueue(self.server_id, record.level, json_line, timestamp)
        except Exception as e:
            # Always report errors through func.report_error
            if func:
                try:
                    asyncio.create_task(func.report_error(e, "addons/logging_manager.py/_emit/enqueue"))
                except Exception:
                    print("Failed scheduling report_error in _emit:", e)
            else:
                print("enqueue error:", e)

        # Render to console if enabled
        try:
            console_cfg = CONFIG.get("console", {})
            if console_cfg.get("enabled", True):
                line = self._format_console_line(record)
                # Only emit colored ANSI sequences if both configured and the runtime supports it.
                if console_cfg.get("color", True) and globals().get("CONSOLE_COLOR_ENABLED", False):
                    # apply color mapping (now produces ANSI sequences)
                    colorized = self._colorize_line(record, line)
                    loguru_logger.log(record.level, colorized)
                else:
                    # Emit plain text message to avoid raw tags or unsupported ANSI codes.
                    loguru_logger.log(record.level, line)
        except Exception as e:
            if func:
                try:
                    asyncio.create_task(func.report_error(e, "addons/logging_manager.py/_emit/console"))
                except Exception:
                    print("console render error:", e)
            else:
                print("console render error:", e)

        # If an exception object passed, also send a structured error record
        if exception is not None:
            try:
                if isinstance(exception, BaseException):
                    exc_text = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
                    # Attach stack trace into extra and write an ERROR-level follow-up record
                    exc_record = LogRecord(
                        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                        level="ERROR",
                        source=self.source,
                        server_id=self.server_id,
                        channel_or_file=str(channel_or_file),
                        user_id=str(user_id) if user_id is not None else "",
                        action="exception",
                        message=str(full_message),
                        trace_id=trace_id,
                        extra={"exception": exc_text},
                    )
                    self._writer.enqueue(self.server_id, exc_record.level, exc_record.to_json_line(), exc_record.timestamp)
                else:
                    # Gracefully handle non-exception objects passed as exception (e.g. from printf-style calls)
                    warn_record = LogRecord(
                        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                        level="WARNING",
                        source=self.source,
                        server_id=self.server_id,
                        channel_or_file=str(channel_or_file),
                        user_id=str(user_id) if user_id is not None else "",
                        action="logging_misuse",
                        message=f"Invalid exception argument passed to logger: {exception!r}",
                        trace_id=trace_id,
                        extra={"invalid_exception_arg": str(exception)},
                    )
                    self._writer.enqueue(self.server_id, warn_record.level, warn_record.to_json_line(), warn_record.timestamp)
            except Exception as e:
                if func:
                    try:
                        asyncio.create_task(func.report_error(e, "addons/logging_manager.py/_emit/exception_dump"))
                    except Exception:
                        print("exception dump error:", e)
                else:
                    print("exception dump error:", e)

    def _format_console_line(self, record: LogRecord) -> str:
        """Create enhanced console representation with simplified timestamp and optional emoji."""
        # Simplify timestamp to HH:MM:SS only
        try:
            dt = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M:%S")
        except Exception:
            time_str = record.timestamp[:8]  # Fallback to first 8 chars
        
        # Get emoji if enabled
        emoji = ""
        if CONFIG.get("use_emoji", True):
            emoji = self._LEVEL_EMOJI.get(record.level, "📝") + " "
        
        # Build parts - only include non-empty fields
        parts = [f"[{time_str}]", f"[{record.level}]", f"[{record.source}]"]
        
        if record.channel_or_file:
            parts.append(f"[{record.channel_or_file}]")
        if record.user_id:
            parts.append(f"[{record.user_id}]")
        
        header = "".join(parts)
        
        # Action and message
        action_part = f"{record.action}" if record.action else ""
        msg_part = f"{record.message}" if record.message else ""
        
        body = " ".join(filter(None, [action_part, msg_part]))
        return f"{emoji}{header} {body}"

    def _colorize_line(self, record: LogRecord, line: str) -> str:
        """Apply ANSI color codes to different parts of the log line for better readability."""
        
        color_map = CONFIG.get("color_map", {})
        level_map = color_map.get("level", {})
        source_map = color_map.get("source", {})
        field_map = color_map.get("fields", {})
        
        # Get colors for different components
        level_color = level_map.get(record.level, "white")
        source_color = source_map.get(record.source, "cyan")
        timestamp_color = field_map.get("timestamp", "bright_black")
        channel_color = field_map.get("channel", "bright_black")
        user_color = field_map.get("user", "bright_black")
        action_color = field_map.get("action", "bright_cyan")
        message_color = field_map.get("message", "white")
        
        # Helper to wrap text with color
        def colorize(text: str, color_name: str) -> str:
            color_code = self._COLORS.get(color_name.lower(), "")
            if not color_code:
                return text
            return f"{color_code}{text}{self._COLORS['reset']}"
        
        try:
            # Simplify timestamp to HH:MM:SS only
            try:
                dt = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                time_str = record.timestamp[:8]
            
            # Get emoji if enabled
            emoji = ""
            if CONFIG.get("use_emoji", True):
                emoji = self._LEVEL_EMOJI.get(record.level, "📝") + " "
            
            # Colorize each component
            timestamp_colored = colorize(f"[{time_str}]", timestamp_color)
            level_colored = colorize(f"[{record.level}]", level_color)
            source_colored = colorize(f"[{record.source}]", source_color)
            
            # Optional fields
            channel_colored = ""
            if record.channel_or_file:
                channel_colored = colorize(f"[{record.channel_or_file}]", channel_color)
            
            user_colored = ""
            if record.user_id:
                user_colored = colorize(f"[{record.user_id}]", user_color)
            
            # Build header
            header_parts = [timestamp_colored, level_colored, source_colored]
            if channel_colored:
                header_parts.append(channel_colored)
            if user_colored:
                header_parts.append(user_colored)
            
            header = "".join(header_parts)
            
            # Action and message
            action_part = ""
            if record.action:
                action_part = colorize(f"{record.action}", action_color)
            
            msg_part = ""
            if record.message:
                msg_part = colorize(f"{record.message}", message_color)
            
            body = " ".join(filter(None, [action_part, msg_part]))
            
            return f"{emoji}{header} {body}"
        
        except Exception:
            # Fallback to simple coloring if parsing fails
            return colorize(line, level_color or "white")

    # Convenience API methods
    def info(self, message: Optional[str] = None, exception: Optional[BaseException] = None, **event_fields: Any) -> None:
        """Emit an INFO event.
 
        Accept both calling styles used across the codebase:
        - logger.info("text", user_id=..., action=..., ...)  (positional message)
        - logger.info(user_id=..., action=..., message="text") (message in kwargs)
        - logger.info("text", message="...") (prefer positional message and avoid duplicate)
        """
        # Normalize message from positional or event_fields, avoid duplicate 'message' key.
        if message is None and "message" in event_fields:
            msg = event_fields.pop("message")
        else:
            # If both provided, prefer positional 'message' and remove kwarg to avoid duplication.
            event_fields.pop("message", None)
            msg = message or ""
        self._emit("INFO", msg, exception, **event_fields)
 
    def warning(self, message: Optional[str] = None, exception: Optional[BaseException] = None, **event_fields: Any) -> None:
        """Emit a WARNING event (handles same calling conventions as info)."""
        if message is None and "message" in event_fields:
            msg = event_fields.pop("message")
        else:
            event_fields.pop("message", None)
            msg = message or ""
        self._emit("WARNING", msg, exception, **event_fields)
 
    def error(self, message: Optional[str] = None, exception: Optional[BaseException] = None, **event_fields: Any) -> None:
        """Emit an ERROR event (handles same calling conventions as info)."""
        if message is None and "message" in event_fields:
            msg = event_fields.pop("message")
        else:
            event_fields.pop("message", None)
            msg = message or ""
        self._emit("ERROR", msg, exception, **event_fields)
 
    def debug(self, message: Optional[str] = None, exception: Optional[BaseException] = None, **event_fields: Any) -> None:
        """Emit a DEBUG event (handles same calling conventions as info)."""
        if message is None and "message" in event_fields:
            msg = event_fields.pop("message")
        else:
            event_fields.pop("message", None)
            msg = message or ""
        self._emit("DEBUG", msg, exception, **event_fields)
    
    def exception(self, message: Optional[str] = None, *args: Any, **event_fields: Any) -> None:
        """Log an ERROR-level event with the current exception traceback (like logging.exception)."""
        # Capture the current exception (if any) and forward it as 'exception' to _emit.
        try:
            exc = sys.exc_info()[1]
        except Exception:
            exc = None
        
        # Handle potential printf-style formatting if args are present
        if args and message:
            try:
                message = message % args
            except Exception:
                # If formatting fails, just append args to message to preserve info
                message = f"{message} {args}"

        if message is None and "message" in event_fields:
            msg = event_fields.pop("message")
        else:
            event_fields.pop("message", None)
            msg = message or ""
        # Use ERROR level and include the captured exception object so stack trace is emitted
        self._emit("ERROR", msg, exc, **event_fields)


# Public API
def get_logger(server_id: Any, source: str = "server", channel: Optional[str] = None) -> LoggerAdapter:
    """Factory returning a bindable logger-like object for a given server_id.

    server_id: string or int representing server/guild id
    source: "server" | "system" | "external"
    channel: optional channel or file name for context
    """
    return LoggerAdapter(server_id=server_id, source=source, channel=channel)


class InterceptHandler(logging.Handler):
    """Logging.Handler that redirects stdlib logging records into our structured logger.

    It routes messages to get_logger(server_id='Bot', source=record.name) while avoiding
    recursion from this module or loguru internals.
    """

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        try:
            # Avoid routing records that originate from our own logging facility or loguru internals.
            name = getattr(record, "name", "")
            if name.startswith("loguru") or name.startswith("addons.logging"):
                return

            # Map logging record to structured logger. Use "Bot" as the system server_id so
            # third-party messages appear in the terminal in the same structured format.
            try:
                adapter = get_logger(server_id="Bot", source=name or "external")
            except Exception as e:
                # If obtaining adapter fails, fallback to printing but report via func.
                if func:
                    try:
                        asyncio.create_task(func.report_error(e, "addons/logging.py/InterceptHandler/get_logger"))
                    except Exception:
                        print("InterceptHandler get_logger error:", e)
                print(f"[InterceptHandler] {name}: {record.getMessage()}")
                return

            # Build extra context from the LogRecord where useful.
            extra = {}
            try:
                args = getattr(record, "args", None)
                # Only merge when args is a mapping/dict. Many libraries use a tuple or string
                # for formatting arguments; attempting to update with those will raise type errors.
                if isinstance(args, dict):
                    extra.update(args)
            except Exception:
                # Best-effort: do not allow merging errors to break log emission.
                pass
            extra.update(
                {
                    "module": getattr(record, "module", ""),
                    "funcName": getattr(record, "funcName", ""),
                    "lineno": getattr(record, "lineno", 0),
                }
            )

            # Capture exception object if available.
            exc = None
            try:
                if record.exc_info:
                    exc = record.exc_info[1]
            except Exception:
                exc = None

            levelname = getattr(record, "levelname", "INFO").upper()
            message = record.getMessage()

            # Dispatch to adapter method if available; otherwise fallback to info.
            try:
                if levelname == "DEBUG":
                    adapter.debug(message, exception=exc, **extra)
                elif levelname in ("WARN", "WARNING"):
                    adapter.warning(message, exception=exc, **extra)
                elif levelname in ("ERROR", "CRITICAL"):
                    adapter.error(message, exception=exc, **extra)
                else:
                    adapter.info(message, exception=exc, **extra)
            except Exception as e:
                # Report any failures when emitting intercepted records.
                if func:
                    try:
                        asyncio.create_task(func.report_error(e, "addons/logging.py/InterceptHandler/emit"))
                    except Exception:
                        print("InterceptHandler emit report error:", e)
                else:
                    print("InterceptHandler emit error:", e)
        except Exception as outer:
            if func:
                try:
                    asyncio.create_task(func.report_error(outer, "addons/logging.py/InterceptHandler/outer"))
                except Exception:
                    print("InterceptHandler outer exception:", outer)
            else:
                print("InterceptHandler outer exception:", outer)


def configure_std_logging() -> None:
    """Configure the standard library logging to route through InterceptHandler and apply third-party levels.

    This function:
    - Removes existing handlers from the root logger.
    - Adds InterceptHandler to capture stdlib logging and funnel it into our structured logger.
    - Attempts to remove non-root handlers to avoid duplicate/unstructured outputs.
    - Applies per-logger level overrides from settings.base_config.logging['third_party_levels'] if present.
    """
    try:
        # Remove all existing handlers on the root logger to avoid duplicate outputs.
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)

        root.setLevel(logging.DEBUG)
        root.addHandler(InterceptHandler())

        # Best-effort: remove handlers from other existing loggers so they don't
        # emit via their own StreamHandler. Set propagate=True so messages bubble
        # to root (our InterceptHandler).
        try:
            manager = getattr(logging, "root").manager
            for name, logger_obj in list(getattr(manager, "loggerDict", {}).items()):
                try:
                    # Some entries in loggerDict are PlaceHolder objects; ensure we have a Logger.
                    if not isinstance(logger_obj, logging.Logger):
                        continue
                    # Avoid touching our own module or loguru internals
                    if name.startswith("addons.logging") or name.startswith("loguru"):
                        continue
                    # Remove handlers attached directly to the logger.
                    if getattr(logger_obj, "handlers", None):
                        for h in list(logger_obj.handlers):
                            try:
                                logger_obj.removeHandler(h)
                            except Exception:
                                pass
                    # Ensure messages propagate to root so InterceptHandler receives them.
                    try:
                        logger_obj.propagate = True
                    except Exception:
                        pass
                except Exception:
                    # Ignore per-logger failures; continue best-effort.
                    continue
        except Exception:
            # If the logging manager introspection fails, continue without raising.
            pass

        # Apply configured levels for noisy third-party libraries.
        third_party_levels = {}
        try:
            base_cfg = getattr(settings, "base_config", None)
            if base_cfg is not None:
                # base_cfg.logging may be a dict
                cfg_dict = getattr(base_cfg, "logging", {}) or {}
                third_party_levels = cfg_dict.get("third_party_levels", {}) or {}
        except Exception:
            third_party_levels = {}

        for logger_name, lvl in (third_party_levels or {}).items():
            try:
                lg = logging.getLogger(logger_name)
                lg.setLevel(str(lvl).upper())
                # Remove handlers attached directly to the logger to avoid duplicate outputs,
                # then ensure propagation to root so InterceptHandler receives the records.
                try:
                    # Prefer clear() where available
                    if getattr(lg, "handlers", None) is not None:
                        lg.handlers.clear()
                except Exception:
                    try:
                        for h in list(getattr(lg, "handlers", []) or []):
                            try:
                                lg.removeHandler(h)
                            except Exception:
                                pass
                    except Exception:
                        pass
                try:
                    lg.propagate = True
                except Exception:
                    pass
                # Special-case: also clear common sqlalchemy sub-loggers to avoid duplicates
                if logger_name == "sqlalchemy":
                    try:
                        for name in ("sqlalchemy.engine", "sqlalchemy.pool"):
                            try:
                                sub = logging.getLogger(name)
                                if getattr(sub, "handlers", None) is not None:
                                    sub.handlers.clear()
                                sub.propagate = True
                            except Exception:
                                # best-effort per-sub-logger cleanup
                                try:
                                    sub = logging.getLogger(name)
                                    for h in list(getattr(sub, "handlers", []) or []):
                                        try:
                                            sub.removeHandler(h)
                                        except Exception:
                                            pass
                                    sub.propagate = True
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except Exception:
                # best-effort only; report but do not raise.
                if func:
                    try:
                        asyncio.create_task(
                            func.report_error(
                                Exception(f"Failed to set level for {logger_name}"),
                                "addons/logging.py/configure_std_logging/level",
                            )
                        )
                    except Exception:
                        print(f"Failed to set level for {logger_name}")
                else:
                    print(f"Failed to set level for {logger_name}")
    except Exception as e:
        if func:
            try:
                asyncio.create_task(func.report_error(e, "addons/logging.py/configure_std_logging"))
            except Exception:
                print("configure_std_logging failed:", e)
        else:
            print("configure_std_logging failed:", e)


# Ensure loguru default handlers are removed as early as possible to avoid verbose initial formatting.
try:
    loguru_logger.remove()
except Exception:
    # best-effort: ignore errors during early removal
    pass

# Perform configuration at import time so that third-party libraries' early logs are captured.
try:
    configure_std_logging()
except Exception as e:
    if func:
        try:
            asyncio.create_task(func.report_error(e, "addons/logging.py/module_init/configure_std_logging"))
        except Exception:
            print("Failed to run configure_std_logging at import:", e)
    else:
        print("Failed to run configure_std_logging at import:", e)