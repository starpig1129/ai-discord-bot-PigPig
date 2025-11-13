"""EpisodicStorage: handles message-related tables (messages, pending_messages, messages_archive).

Extracted from the previous sqlite_storage implementation to separate concerns.
All error reporting uses func.report_error per project rules.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from .connection import DatabaseConnection
from function import func

logger = logging.getLogger(__name__)


class EpisodicStorage:
    """Handles messages, pending_messages and messages_archive tables."""

    def __init__(self, db: DatabaseConnection) -> None:
        self.db = db
        self.logger = logger

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
                result: List[Dict[str, Any]] = []
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
                result: List[Dict[str, Any]] = []
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

    async def archive_messages(self, message_ids: List[int]) -> None:
        """Archive messages by moving them from `messages` into `messages_archive`.

        Operation is performed inside a single transaction to ensure consistency:
          1. Select rows for the provided message_ids from `messages`.
          2. Insert those rows into `messages_archive` with an `archived_at` timestamp.
          3. Delete the archived rows from `messages`.
        """
        if not message_ids:
            return

        try:
            placeholders = ",".join("?" for _ in message_ids)
            select_sql = f"SELECT message_id, channel_id, guild_id, user_id, content, timestamp, reactions FROM messages WHERE message_id IN ({placeholders})"
            insert_sql = """
            INSERT OR REPLACE INTO messages_archive
            (message_id, channel_id, guild_id, user_id, content, timestamp, reactions, archived_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            delete_sql = f"DELETE FROM messages WHERE message_id IN ({placeholders})"

            with self.db.get_connection() as conn:
                cursor = conn.execute(select_sql, message_ids)
                rows = cursor.fetchall()
                if not rows:
                    # Nothing to archive
                    return

                # Insert each row into archive with current UTC timestamp (seconds since epoch)
                archived_at = datetime.utcnow().timestamp()
                for r in rows:
                    conn.execute(
                        insert_sql,
                        (
                            r["message_id"],
                            r["channel_id"],
                            r["guild_id"],
                            r["user_id"],
                            r["content"],
                            r["timestamp"],
                            r["reactions"],
                            archived_at,
                        ),
                    )

                # Delete archived rows from primary table
                conn.execute(delete_sql, message_ids)
                conn.commit()
        except Exception as e:
            await func.report_error(e, "archive_messages failed")

    async def delete_messages(self, message_ids: List[int]) -> None:
        """Delete messages directly from the primary `messages` table.

        This is used for data retention policies that require permanent deletion.
        """
        if not message_ids:
            return
        try:
            placeholders = ",".join("?" for _ in message_ids)
            delete_sql = f"DELETE FROM messages WHERE message_id IN ({placeholders})"
            with self.db.get_connection() as conn:
                conn.execute(delete_sql, message_ids)
                conn.commit()
        except Exception as e:
            await func.report_error(e, "delete_messages failed")