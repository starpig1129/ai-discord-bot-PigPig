# addons/logging_manager.py
# Core logging manager implementing structured NDJSON sinks and console rendering.
#
# English comments only. Conforms to project rules (use func.report_error for error reporting)
# and loads configuration from addons.settings.

import asyncio
import json
import os
import threading
import time
import traceback
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

# Load logging configuration from settings.base_config.logging if available.
_LOG_CFG: Dict[str, Any] = {}
# Safely obtain logging config whether base_config is an object or a dict.
base_cfg = getattr(settings, "base_config", None)
if isinstance(base_cfg, dict):
    # base_config provided as a dict
    _LOG_CFG = base_cfg.get("logging", {}) or {}
elif base_cfg is not None:
    # base_config provided as an object with attributes
    try:
        _LOG_CFG = getattr(base_cfg, "logging", {}) or {}
    except Exception:
        _LOG_CFG = {}
else:
    # No base_config found; fallback to empty
    _LOG_CFG = {}

# Defaults (match plan.md defaults)
_DEFAULTS = {
    "console": {"enabled": True, "color": True},
    "color_map": {
        "level": {"ERROR": "red", "WARNING": "yellow", "INFO": "green", "DEBUG": "cyan"},
        "source": {"system": "magenta", "external": "blue"},
    },
    "async": {"batch_size": 500, "flush_interval": 2.0},
    "rotation": {"policy": "daily", "compress": True, "retention_days": 300},
    "per_level_retention": {"INFO": 300, "WARNING": 300, "ERROR": 900},
    "fsync_on_flush": False,
    "log_base_path": "logs",
}

# Merge defaults with provided config (shallow merge is sufficient for our keys)
CONFIG = {**_DEFAULTS, **_LOG_CFG}
CONFIG["console"] = {**_DEFAULTS["console"], **CONFIG.get("console", {})}
CONFIG["color_map"] = {**_DEFAULTS["color_map"], **CONFIG.get("color_map", {})}
CONFIG["async"] = {**_DEFAULTS["async"], **CONFIG.get("async", {})}

# Configure loguru console sink: simple message-only single-line output.
# Remove existing handlers and add a minimal one to keep console rendering predictable.
try:
    loguru_logger.remove()
    loguru_logger.add(
        sink=lambda msg: print(msg, end=""),
        format="{message}",
        colorize=True,
        level="DEBUG",
    )
except Exception:
    # If configuring loguru fails, report and continue without raising.
    if func:
        try:
            asyncio.create_task(func.report_error(Exception("loguru init failed"), "addons/logging_manager.py/init"))
        except Exception:
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
                filename = os.path.join(log_dir, f"bot_log_{level}.jsonl")
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
                filename = os.path.join(log_dir, f"bot_log_{level}.jsonl")
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
                if console_cfg.get("color", True):
                    # apply color mapping
                    colorized = self._colorize_line(record, line)
                    # loguru will handle ANSI tags like <green>...</green>
                    loguru_logger.log(record.level, colorized)
                else:
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
            except Exception as e:
                if func:
                    try:
                        asyncio.create_task(func.report_error(e, "addons/logging_manager.py/_emit/exception_dump"))
                    except Exception:
                        print("exception dump error:", e)
                else:
                    print("exception dump error:", e)

    def _format_console_line(self, record: LogRecord) -> str:
        """Create the single-line console representation described in plan.md."""
        # [timestamp][level][source][channel_or_file][user_id] action=... message=...
        parts = [
            f"[{record.timestamp}]",
            f"[{record.level}]",
            f"[{record.source}]",
            f"[{record.channel_or_file}]",
            f"[{record.user_id}]",
        ]
        header = "".join(parts)
        action_part = f"action={record.action}" if record.action else "action="
        msg_part = f"message={record.message}"
        return f"{header} {action_part} {msg_part}"

    def _colorize_line(self, record: LogRecord, line: str) -> str:
        """Apply color tags according to CONFIG color_map for level and source."""
        color_map = CONFIG.get("color_map", {})
        level_map = color_map.get("level", {})
        source_map = color_map.get("source", {})
        level_color = level_map.get(record.level, "")
        source_color = source_map.get(record.source, "")
        # Wrap different segments in color tags if available.
        # Priority: level color for the whole line; if absent, try source color.
        if level_color:
            return f"<{level_color}>{line}</{level_color}>"
        if source_color:
            return f"<{source_color}>{line}</{source_color}>"
        return line

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


# Public API
def get_logger(server_id: Any, source: str = "server", channel: Optional[str] = None) -> LoggerAdapter:
    """Factory returning a bindable logger-like object for a given server_id.

    server_id: string or int representing server/guild id
    source: "server" | "system" | "external"
    channel: optional channel or file name for context
    """
    return LoggerAdapter(server_id=server_id, source=source, channel=channel)