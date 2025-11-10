"""Database connection manager for the memory cog.

Handles SQLite connection lifecycle, thread-safe access, and error reporting.
"""
import asyncio
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional, Union

from function import func
from ..exceptions import DatabaseError
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import PigPig


class DatabaseConnection:
    """Manage SQLite connections per-thread and provide thread-safe access."""

    def __init__(self, db_path: Union[str, Path], bot: Optional["PigPig"] = None):
        """Initialize connection manager.

        This class intentionally does not create database schema; schema creation
        belongs to schema.create_tables.
        """
        self.db_path = Path(db_path)
        self.bot = bot
        self._loop = None
        self.logger = logging.getLogger(__name__)
        self._lock = threading.RLock()
        self._connections: Dict[int, sqlite3.Connection] = {}

        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _report_error_threadsafe(self, exc: Exception, ctx: str) -> None:
        """Report errors in a thread-safe manner to the async error reporter.

        If an event loop is available, submit func.report_error via
        asyncio.run_coroutine_threadsafe; otherwise fall back to logger.
        """
        try:
            if self._loop:
                try:
                    asyncio.run_coroutine_threadsafe(func.report_error(exc, ctx), self._loop)
                except Exception:
                    try:
                        self.logger.exception("Failed to submit async error report, falling back to logger")
                        self.logger.exception("%s: %s", ctx, exc)
                    except Exception:
                        pass
            else:
                try:
                    self.logger.exception("%s (no loop): %s", ctx, exc)
                except Exception:
                    pass
        except Exception:
            try:
                self.logger.exception("Error while reporting DB error")
            except Exception:
                pass

    @contextmanager
    def get_connection(self):
        """Context manager that yields a sqlite3.Connection bound to the current thread."""
        thread_id = threading.get_ident()

        with self._lock:
            if thread_id not in self._connections:
                try:
                    conn = sqlite3.connect(
                        str(self.db_path),
                        check_same_thread=False,
                        timeout=30.0
                    )
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("PRAGMA journal_mode = WAL")
                    conn.execute("PRAGMA synchronous = NORMAL")

                    self._connections[thread_id] = conn
                except Exception as e:
                    self.logger.debug("DB except: no loop=%s thread=%s", self._loop is None, threading.get_ident())
                    self._report_error_threadsafe(e, "Failed to create database connection")
                    raise DatabaseError(f"Failed to create database connection: {e}")

            conn = self._connections[thread_id]

        try:
            yield conn
        except Exception as e:
            # Attempt to rollback and capture schema snapshot for diagnostics.
            try:
                conn.rollback()
            except Exception as rb_exc:
                self.logger.warning("DB rollback failed: %s", rb_exc)

            self.logger.debug("DB except: no loop=%s thread=%s", self._loop is None, threading.get_ident())

            schema_info = {}
            try:
                try:
                    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                except Exception:
                    tables = None
                try:
                    users_schema_rows = conn.execute("PRAGMA table_info('users')").fetchall()
                    users_schema = []
                    for r in users_schema_rows:
                        try:
                            users_schema.append(dict(r))
                        except Exception:
                            users_schema.append(tuple(r))
                except Exception:
                    users_schema = None
                schema_info = {"tables": tables, "users_schema": users_schema}
                self.logger.error("Database operation failed, schema snapshot: %s", schema_info)
            except Exception as schema_exc:
                self.logger.warning("Failed to obtain schema snapshot: %s", schema_exc)
                schema_info = f"schema dump failed: {schema_exc}"

            try:
                self._report_error_threadsafe(e, f"Database operation failed; schema: {schema_info}")
            except Exception:
                try:
                    self.logger.exception("Failed to thread-safe report DB error: %s", e)
                except Exception:
                    pass

            raise DatabaseError(f"Database operation failed: {e}")

    def close_connections(self) -> None:
        """Close all managed SQLite connections."""
        with self._lock:
            for thread_id, conn in list(self._connections.items()):
                try:
                    conn.close()
                except Exception as e:
                    self.logger.warning("Error closing connection for thread %s: %s", thread_id, e)
            self._connections.clear()
            self.logger.info("All database connections closed")