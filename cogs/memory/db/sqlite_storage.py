"""SQLiteStorage: concrete StorageInterface implementation using SQLite.

This module centralizes SQL logic previously spread across user_manager.py
and earlier database modules into a single storage implementation.
All error reporting uses func.report_error per project rules.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..interfaces.storage_interface import StorageInterface
from ..user_manager import UserInfo
from .connection import DatabaseConnection
from .schema import create_tables
from function import func

logger = logging.getLogger(__name__)


class SQLiteStorage(StorageInterface):
    """Concrete storage backed by a SQLite database."""

    def __init__(self, db_path: str, bot: Optional[Any] = None) -> None:
        """
        Initialize storage.

        Args:
            db_path: Path to sqlite database file.
            bot: Optional bot instance passed to DatabaseConnection for error reporting.
        """
        self.db = DatabaseConnection(db_path, bot)
        self._user_cache: Dict[str, UserInfo] = {}
        self._cache_size_limit = 1000
        # Ensure schema exists
        try:
            with self.db.get_connection() as conn:
                create_tables(conn)
        except Exception as e:
            # Non-blocking report; raise so caller knows initialization failed.
            asyncio.create_task(func.report_error(e, "Failed to create or verify DB tables"))
            raise

    # -----------------------
    # User-related operations
    # -----------------------
    async def get_user_info(self, user_id: str) -> Optional[UserInfo]:
        """Retrieve user info (combines users and user_profiles)."""
        # Check cache first
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT u.user_id, u.username AS display_name, u.created_at,
                           up.profile_data
                    FROM users u
                    LEFT JOIN user_profiles up ON u.user_id = up.user_id
                    WHERE u.user_id = ?
                    """,
                    (user_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                profile_data = None
                if row["profile_data"]:
                    try:
                        profile_data = json.loads(row["profile_data"])
                    except json.JSONDecodeError:
                        logger.warning("Failed to decode profile_data for user %s", user_id)

                created_at = None
                if row["created_at"]:
                    try:
                        created_at = datetime.fromtimestamp(float(row["created_at"]))
                    except Exception:
                        created_at = None

                user_info = UserInfo(
                    user_id=str(row["user_id"]),
                    display_name=row["display_name"] or "",
                    user_data=None,
                    last_active=None,
                    profile_data=profile_data,
                    preferences=None,
                    created_at=created_at,
                )

                # update cache
                self._update_cache(user_id, user_info)
                return user_info
        except Exception as e:
            await func.report_error(e, f"get_user_info failed (user: {user_id})")
            return None

    async def update_user_data(self, user_id: str, user_data: str, display_name: str) -> bool:
        """Insert or update a user's data and display name."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                exists = cursor.fetchone() is not None

                if exists:
                    conn.execute(
                        """
                        UPDATE users
                        SET username = COALESCE(?, username),
                            created_at = COALESCE(?, created_at)
                        WHERE user_id = ?
                        """,
                        (display_name, None, user_id),
                    )
                else:
                    now_ts = datetime.utcnow().timestamp()
                    conn.execute(
                        """
                        INSERT INTO users (user_id, username, is_bot, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (user_id, display_name, 0, now_ts),
                    )
                conn.commit()

                # invalidate cache
                if user_id in self._user_cache:
                    del self._user_cache[user_id]
                return True
        except sqlite3.IntegrityError as ie:
            await func.report_error(ie, f"Integrity error updating user {user_id}")
            return False
        except Exception as e:
            await func.report_error(e, f"update_user_data failed (user: {user_id})")
            return False

    async def update_user_activity(self, user_id: str, display_name: str) -> bool:
        """Update user's activity timestamp and optionally display name."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                exists = cursor.fetchone() is not None

                now_ts = datetime.utcnow().timestamp()
                if exists:
                    conn.execute(
                        """
                        UPDATE users
                        SET created_at = COALESCE(?, created_at),
                            username = COALESCE(?, username)
                        WHERE user_id = ?
                        """,
                        (now_ts, display_name, user_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO users (user_id, username, is_bot, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (user_id, display_name, 0, now_ts),
                    )
                conn.commit()

                if user_id in self._user_cache:
                    del self._user_cache[user_id]
                return True
        except Exception as e:
            await func.report_error(e, f"update_user_activity failed (user: {user_id})")
            return False

    # -----------------------
    # Pending message queue
    # -----------------------
    async def add_pending_message(self, message: Any) -> None:
        """Add a discord.Message to pending_messages for later processing."""
        try:
            message_id = getattr(message, "id", None)
            channel_id = getattr(message.channel, "id", None)
            guild = getattr(message, "guild", None)
            guild_id = getattr(guild, "id", 0) if guild is not None else 0
            user_id = getattr(message.author, "id", None)
            timestamp = getattr(message, "created_at", None)
            ts_val = timestamp.timestamp() if timestamp is not None else datetime.utcnow().timestamp()

            with self.db.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO pending_messages (message_id, channel_id, guild_id, user_id, timestamp, processed)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (message_id, channel_id, guild_id, user_id, ts_val),
                )
                conn.commit()
        except Exception as e:
            await func.report_error(e, "add_pending_message failed")

    async def get_pending_messages(self, limit: int) -> List[Dict[str, Any]]:
        """Retrieve pending messages (not processed)."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, message_id, channel_id, guild_id, user_id, timestamp FROM pending_messages WHERE processed = 0 ORDER BY id ASC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                result = []
                for r in rows:
                    result.append(
                        {
                            "id": int(r["id"]),
                            "message_id": int(r["message_id"]),
                            "channel_id": int(r["channel_id"]),
                            "guild_id": int(r["guild_id"]),
                            "user_id": int(r["user_id"]),
                            "timestamp": float(r["timestamp"]),
                        }
                    )
                return result
        except Exception as e:
            await func.report_error(e, "get_pending_messages failed")
            return []

    async def mark_pending_messages_processed(self, pending_ids: List[int]) -> None:
        """Mark pending messages as processed by their pending_messages.id values."""
        if not pending_ids:
            return
        try:
            placeholders = ",".join("?" for _ in pending_ids)
            with self.db.get_connection() as conn:
                conn.execute(f"UPDATE pending_messages SET processed = 1 WHERE id IN ({placeholders})", pending_ids)
                conn.commit()
        except Exception as e:
            await func.report_error(e, "mark_pending_messages_processed failed")

    # -----------------------
    # Message storage / vectorization
    # -----------------------
    async def store_messages_batch(self, messages: List[Any]) -> None:
        """Store a batch of messages for future vectorization."""
        try:
            with self.db.get_connection() as conn:
                for message in messages:
                    message_id = getattr(message, "id", None)
                    channel_id = getattr(message.channel, "id", None)
                    guild = getattr(message, "guild", None)
                    guild_id = getattr(guild, "id", 0) if guild is not None else 0
                    user_id = getattr(message.author, "id", None)
                    content = getattr(message, "content", "") or ""
                    timestamp = getattr(message, "created_at", None)
                    ts_val = timestamp.timestamp() if timestamp is not None else datetime.utcnow().timestamp()

                    # reactions: store a simple JSON summary if available
                    reactions = None
                    react_list = getattr(message, "reactions", None)
                    if react_list:
                        try:
                            simple = []
                            for r in react_list:
                                try:
                                    emoji = getattr(r.emoji, "name", str(r.emoji))
                                except Exception:
                                    emoji = str(r.emoji)
                                # count may not be available synchronously; skip if not present
                                count = getattr(r, "count", None)
                                simple.append({"emoji": emoji, "count": count})
                            reactions = json.dumps(simple, ensure_ascii=False)
                        except Exception:
                            reactions = None

                    conn.execute(
                        """
                        INSERT OR REPLACE INTO messages
                        (message_id, channel_id, guild_id, user_id, content, timestamp, reactions, vectorized)
                        VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT vectorized FROM messages WHERE message_id = ?), 0))
                        """,
                        (message_id, channel_id, guild_id, user_id, content, ts_val, reactions, message_id),
                    )
                conn.commit()
        except Exception as e:
            await func.report_error(e, "store_messages_batch failed")

    async def get_unprocessed_messages(self, limit: int) -> List[Dict[str, Any]]:
        """Get messages that have not been vectorized yet."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT message_id, channel_id, guild_id, user_id, content, timestamp, reactions FROM messages WHERE vectorized = 0 ORDER BY timestamp ASC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                result = []
                for r in rows:
                    result.append(
                        {
                            "message_id": int(r["message_id"]),
                            "channel_id": int(r["channel_id"]),
                            "guild_id": int(r["guild_id"]),
                            "user_id": int(r["user_id"]),
                            "content": r["content"],
                            "timestamp": float(r["timestamp"]),
                            "reactions": json.loads(r["reactions"]) if r["reactions"] else None,
                        }
                    )
                return result
        except Exception as e:
            await func.report_error(e, "get_unprocessed_messages failed")
            return []

    async def mark_messages_vectorized(self, message_ids: List[int]) -> None:
        """Mark messages as vectorized."""
        if not message_ids:
            return
        try:
            placeholders = ",".join("?" for _ in message_ids)
            with self.db.get_connection() as conn:
                conn.execute(f"UPDATE messages SET vectorized = 1 WHERE message_id IN ({placeholders})", message_ids)
                conn.commit()
        except Exception as e:
            await func.report_error(e, "mark_messages_vectorized failed")

    # -----------------------
    # Config storage
    # -----------------------
    async def get_config(self, key: str) -> Optional[str]:
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row["value"] if row else None
        except Exception as e:
            await func.report_error(e, f"get_config failed (key: {key})")
            return None

    async def set_config(self, key: str, value: str) -> None:
        try:
            with self.db.get_connection() as conn:
                conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
                conn.commit()
        except Exception as e:
            await func.report_error(e, f"set_config failed (key: {key})")

    # -----------------------
    # Helpers
    # -----------------------
    def _update_cache(self, user_id: str, user_info: UserInfo) -> None:
        """Update in-memory cache with eviction policy."""
        try:
            if len(self._user_cache) >= self._cache_size_limit:
                # remove oldest entry
                oldest = next(iter(self._user_cache))
                del self._user_cache[oldest]
            self._user_cache[user_id] = user_info
        except Exception as e:
            # avoid awaiting in synchronous helper; spawn a task
            asyncio.create_task(func.report_error(e, "cache update failed"))