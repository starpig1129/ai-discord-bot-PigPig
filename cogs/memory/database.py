"""記憶系統資料庫管理模組

提供 SQLite 資料庫的建立、連接、操作和管理功能。
實作執行緒安全的資料庫操作和連接池管理。
"""

import asyncio
import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import discord

from function import func
from .exceptions import DatabaseError

if TYPE_CHECKING:
    from bot import PigPig


class DatabaseManager:
    """資料庫管理器
    
    負責 SQLite 資料庫的建立、連接管理和基本 CRUD 操作。
    實作連接池和執行緒安全機制。
    """
    
    def __init__(self, db_path: Union[str, Path], bot: Optional["PigPig"] = None):
        """初始化資料庫管理器

        Args:
            db_path: 資料庫檔案路徑
            bot: 機器人實例（可選，用於錯誤報告）
        """
        self.db_path = Path(db_path)
        self.bot = bot
        # 儲存 bot 的事件迴圈引用（若有），以便在同步路徑 thread-safe 地提交 coroutine
        self._loop = getattr(self.bot, "loop", None) if bot else None
        self.logger = logging.getLogger(__name__)
        self._lock = threading.RLock()
        self._connections: Dict[int, sqlite3.Connection] = {}
        
        # 延遲初始化使用者管理器（避免循環導入）
        self._user_manager = None
        
        # 確保資料庫目錄存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化資料庫
        self._initialize_database()
    
    @property
    def user_manager(self):
        """取得使用者管理器（延遲初始化）"""
        if self._user_manager is None:
            from .user_manager import SQLiteUserManager
            self._user_manager = SQLiteUserManager(self)
        return self._user_manager
    
    def _initialize_database(self) -> None:
        """Initializes the database structure by creating tables."""
        try:
            with self.get_connection() as conn:
                self._create_tables(conn)
                conn.commit()
            self.logger.info(f"Database initialized successfully: {self.db_path}")
        except Exception as e:
            self.logger.debug("DB except: no loop=%s thread=%s", self._loop is None, threading.get_ident())
            self._report_error_threadsafe(e, "Database initialization failed")
            raise DatabaseError(f"Database initialization failed: {e}")

    def _report_error_threadsafe(self, exc: Exception, ctx: str) -> None:
        """在同步/執行緒上下文中安全地回報錯誤給異步錯誤報告服務。

        1) 若有可用的事件迴圈（self._loop），使用
           asyncio.run_coroutine_threadsafe(...) 提交 coroutine；
        2) 否則降級為同步 logger 記錄，
           並捕捉任何在提交時發生的例外以避免在 except path 再拋出。
        """
        try:
            if self._loop:
                try:
                    asyncio.run_coroutine_threadsafe(func.report_error(exc, ctx), self._loop)
                except Exception:
                    # 若提交失敗，降級為同步記錄，且不再拋出
                    try:
                        self.logger.exception("Failed to submit async error report, falling back to logger")
                        self.logger.exception("%s: %s", ctx, exc)
                    except Exception:
                        # 最後防護：避免在 error-report path 再次爆炸
                        pass
            else:
                # 沒有事件迴圈，直接同步記錄
                try:
                    self.logger.exception("%s (no loop): %s", ctx, exc)
                except Exception:
                    pass
        except Exception:
            # 最後防護：確保不在 except path 再爆炸
            try:
                self.logger.exception("Error while reporting DB error")
            except Exception:
                pass

    @contextmanager
    def get_connection(self):
        """取得資料庫連接 (上下文管理器)
        
        Yields:
            sqlite3.Connection: 資料庫連接
        """
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
                    # 啟用外鍵約束
                    conn.execute("PRAGMA foreign_keys = ON")
                    # 設定 WAL 模式提升並發性能
                    conn.execute("PRAGMA journal_mode = WAL")
                    # 設定同步模式
                    conn.execute("PRAGMA synchronous = NORMAL")
                    
                    self._connections[thread_id] = conn
                    
                except Exception as e:
                    self.logger.debug("DB except: no loop=%s thread=%s", self._loop is None, threading.get_ident())
                    self._report_error_threadsafe(e, "建立資料庫連接失敗")
                    raise DatabaseError(f"建立資料庫連接失敗: {e}")
            
            conn = self._connections[thread_id]
        
        try:
            yield conn
        except Exception as e:
            # 回滾交易並嘗試收集 schema 快照以協助診斷（若可用）
            try:
                conn.rollback()
            except Exception as rb_exc:
                # 即使回滾失敗，也要繼續嘗試記錄原始錯誤與 schema
                self.logger.warning("DB rollback failed: %s", rb_exc)
            self.logger.debug("DB except: no loop=%s thread=%s", self._loop is None, threading.get_ident())
    
            # 嘗試取得資料表清單與 users 表結構以做診斷（失敗時繼續，不阻斷原錯誤拋出）
            schema_info = {}
            try:
                try:
                    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                except Exception:
                    tables = None
                try:
                    users_schema_rows = conn.execute("PRAGMA table_info('users')").fetchall()
                    # 將 sqlite3.Row 轉為簡單 dict 列表供日誌輸出
                    users_schema = []
                    for r in users_schema_rows:
                        try:
                            users_schema.append(dict(r))
                        except Exception:
                            # fallback: 將 row 轉為 tuple
                            users_schema.append(tuple(r))
                except Exception:
                    users_schema = None
                schema_info = {"tables": tables, "users_schema": users_schema}
                self.logger.error("資料庫操作失敗，schema snapshot: %s", schema_info)
            except Exception as schema_exc:
                self.logger.warning("無法取得 schema snapshot: %s", schema_exc)
                schema_info = f"schema dump failed: {schema_exc}"
    
            # 使用 thread-safe 的回報機制上報原始錯誤並夾帶 schema 訊息
            try:
                self._report_error_threadsafe(e, f"資料庫操作失敗; schema: {schema_info}")
            except Exception:
                # 若回報也失敗，記錄到 logger（避免在 except path 再次崩潰）
                try:
                    self.logger.exception("Failed to thread-safe report DB error: %s", e)
                except Exception:
                    pass
    
            # 最後包裝並拋出 DatabaseError
            raise DatabaseError(f"資料庫操作失敗: {e}")

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Creates all necessary tables and indexes if they don't exist."""
        cursor = conn.cursor()
        # Table for storing user information
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                is_bot INTEGER NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        # Table for storing user profiles (e.g., custom system prompts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                profile_data TEXT,
                updated_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        """)
        # Table for pending messages to be processed by the LLM
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                processed INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_messages_processed ON pending_messages (processed)")
        
        # Table for storing full message content for vectorization
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                reactions TEXT,
                vectorized INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages (user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_vectorized ON messages (vectorized)")
        
        # Table for system configuration
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self.logger.info("Database tables created or verified successfully.")

    async def add_pending_message(self, message: discord.Message) -> None:
        """Adds a message to the pending queue for processing."""
        if not message.guild:
            return
        with self._lock:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO pending_messages
                    (message_id, channel_id, guild_id, user_id, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (message.id, message.channel.id, message.guild.id, message.author.id, message.created_at.timestamp())
                )
                conn.commit()

    async def get_pending_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves a batch of unprocessed pending messages."""
        with self._lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, message_id, channel_id, guild_id FROM pending_messages WHERE processed = 0 ORDER BY timestamp ASC LIMIT ?",
                    (limit,)
                )
                return [dict(row) for row in cursor.fetchall()]

    async def count_pending_messages(self) -> int:
        """Counts the total number of unprocessed pending messages."""
        with self._lock:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM pending_messages WHERE processed = 0")
                count = cursor.fetchone()[0]
                return count if count is not None else 0

    async def mark_pending_messages_processed(self, pending_ids: List[int]) -> None:
        """Marks a batch of pending messages as processed."""
        if not pending_ids:
            return
        with self._lock:
            with self.get_connection() as conn:
                conn.executemany(
                    "UPDATE pending_messages SET processed = 1 WHERE id = ?",
                    [(pid,) for pid in pending_ids]
                )
                conn.commit()

    async def mark_pending_message_processed(self, pending_id: int) -> None:
        """Marks a single pending message as processed."""
        with self._lock:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE pending_messages SET processed = 1 WHERE id = ?",
                    (pending_id,)
                )
                conn.commit()

    async def store_messages_batch(self, messages: List[discord.Message]) -> None:
        """Stores a batch of full message objects for later vectorization."""
        if not messages:
            return
        
        values = []
        for msg in messages:
            if not msg.guild:
                continue
            reactions_json = json.dumps([str(r.emoji) for r in msg.reactions])
            values.append((
                msg.id, msg.channel.id, msg.guild.id, msg.author.id,
                msg.content, msg.created_at.timestamp(), reactions_json
            ))

        if not values:
            return

        with self._lock:
            with self.get_connection() as conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO messages
                    (message_id, channel_id, guild_id, user_id, content, timestamp, reactions)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    values
                )
                conn.commit()

    async def get_unprocessed_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves a batch of messages that have not yet been vectorized."""
        with self._lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT message_id, content FROM messages WHERE vectorized = 0 LIMIT ?",
                    (limit,)
                )
                return [dict(row) for row in cursor.fetchall()]

    async def mark_messages_vectorized(self, message_ids: List[int]) -> None:
        """Marks a batch of messages as vectorized."""
        if not message_ids:
            return
        with self._lock:
            with self.get_connection() as conn:
                conn.executemany(
                    "UPDATE messages SET vectorized = 1 WHERE message_id = ?",
                    [(mid,) for mid in message_ids]
                )
                conn.commit()

    async def get_config(self, key: str) -> Optional[str]:
        """Retrieves a configuration value from the database."""
        with self._lock:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row['value'] if row else None

    async def set_config(self, key: str, value: str) -> None:
        """Sets a configuration value in the database."""
        with self._lock:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                    (key, value)
                )
                conn.commit()

    def close_connections(self) -> None:
        """關閉所有資料庫連接"""
        with self._lock:
            for thread_id, conn in self._connections.items():
                try:
                    conn.close()
                except Exception as e:
                    self.logger.warning(f"關閉執行緒 {thread_id} 的連接時發生錯誤: {e}")
            self._connections.clear()
            self.logger.info("所有資料庫連接已關閉")
