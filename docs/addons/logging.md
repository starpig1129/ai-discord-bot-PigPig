# Logging Manager (addons/logging_manager.py)

This document describes the new structured logging system used by the project. The implementation lives in `addons/logging_manager.py` and is configured via `addons/settings.py` (see `BaseConfig.logging`).

## Overview

- Outputs structured NDJSON to per-server, per-day files: `logs/<server_id>/<YYYYMMDD>/bot_log_<LEVEL>.jsonl`.
- Console output is a single-line human readable format:
  [timestamp][level][source][channel_or_file][user_id] action=... message=...
- Background writer batches writes for high throughput and low syscall overhead.
- Public API: `get_logger(server_id, source='server', channel=None) -> logger-like adapter`

## Getting a Logger

Import and create a logger for a server (or "system"):

[`python`](addons/logging_manager.py:448)
from addons.logging_manager import get_logger

log = get_logger(server_id=123, source="server", channel="general")

The returned object supports:
- .info(message, exception=None, **event_fields)
- .warning(...)
- .error(...)
- .debug(...)
- .bind(**context) -> returns a new adapter with merged bound context

Example:
[`python`](addons/logging_manager.py:66)
log.info("User sent message", user_id=456, action="send", message="hello", trace_id="abc123")

## Structured NDJSON Schema

Each line is a single JSON object with fields:

- timestamp: ISO 8601 UTC (e.g. 2025-11-17T08:00:00Z)
- level: INFO/WARNING/ERROR/DEBUG
- source: server/system/external
- server_id: string or integer
- channel_or_file: string
- user_id: string or integer
- action: short verb
- message: text
- trace_id: optional request/correlation id
- extra: dictionary with any vendor-specific fields

Example NDJSON line:
{"timestamp":"2025-11-17T08:00:00Z","level":"INFO","source":"server","server_id":"123","channel_or_file":"general","user_id":"456","action":"send","message":"hello","trace_id":"abc123","extra":{}}

## Console Renderer

Console single-line format (used when console enabled in config):

[timestamp][level][source][channel_or_file][user_id] action=... message=...

Colorization is applied using the `color_map` in configuration and is handled by `loguru` tags.

## Configuration (addons/settings.py)

The logging configuration is exposed via `addons.settings.base_config.logging` (loaded into `addons.settings.BaseConfig.logging`). Key options:

- console:
  - enabled: bool — enable console rendering
  - color: bool — use color tags for console output

- color_map:
  - level: map from level name (e.g., "ERROR") to color name (e.g., "red")
  - source: map from source (e.g., "system") to color name

- async:
  - batch_size: int — number of records to batch before write
  - flush_interval: float — seconds to wait before flushing if batch not full

- rotation:
  - policy: "daily" (informational; rotation implemented externally)
  - compress: bool
  - retention_days: int

- per_level_retention:
  - mapping for retention days by level, e.g. {"INFO": 300, "ERROR": 900}

- fsync_on_flush: bool — best-effort fsync on each flush (off by default)

- log_base_path: string — base directory for logs (default: "logs")

Example configuration fragment (placed in base YAML under `logging` section):
[`python`](addons/settings.py:67)
LOGGING = {
    "console": {"enabled": True, "color": True},
    "color_map": {
        "level": {"ERROR": "red", "WARNING": "yellow", "INFO": "green", "DEBUG": "cyan"},
        "source": {"system": "magenta", "external": "blue"}
    },
    "async": {"batch_size": 500, "flush_interval": 2.0},
    "rotation": {"policy": "daily", "compress": True, "retention_days": 300},
    "per_level_retention": {"INFO": 300, "WARNING": 300, "ERROR": 900},
    "fsync_on_flush": False,
    "log_base_path": "logs",
}

## Testing

Unit and integration tests for the logging manager were added under `tests/test_logging_manager.py`. Tests include:
- NDJSON serialization correctness
- Console line format correctness
- Background writer writes per-level files
- A light-load integration test that writes multiple events and verifies file output

See `tests/test_logging_manager.py` for implementation details.

## Operational Notes

- Background writer runs in a dedicated daemon thread and uses a bounded queue to avoid unbounded memory growth. When the queue is full events are dropped and reported using `func.report_error` (project-wide error reporting helper).
- For retention and rotation, perform daily compression and cleanup with a scheduled job or small maintenance script; these operations are intentionally kept out of the write path for performance.
- Do not log sensitive PII or tokens. Add redaction hooks prior to emitting structured events if necessary.

## Migration

The compatibility shim `logs.py` was used during migration but should be removed once all code uses `get_logger`. The new API is stable and recommended for all modules.

## References

- Implementation: [`addons/logging_manager.py`](addons/logging_manager.py:1)
- Configuration object: [`addons/settings.py`](addons/settings.py:1)
- Design plan: [`plan.md`](plan.md:1)