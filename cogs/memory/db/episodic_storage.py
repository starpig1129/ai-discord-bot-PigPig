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
    """Handles channel memory state management."""

    def __init__(self, db: DatabaseConnection) -> None:
        self.db = db
        self.logger = logger

    async def initialize_channel_memory_state(self) -> None:
        """Initialize the channel_memory_state table in the database."""
        try:
            with self.db.get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS channel_memory_state (
                        channel_id INTEGER PRIMARY KEY,
                        message_count INTEGER NOT NULL DEFAULT 0,
                        start_message_id INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            await func.report_error(e, "initialize_channel_memory_state failed")

    async def get_channel_memory_state(self, channel_id: int) -> Optional[Dict[str, int]]:
        """Get the memory state for a specific channel.
        
        Args:
            channel_id (int): The channel ID to get state for.
            
        Returns:
            Optional[Dict[str, int]]: Dictionary with 'message_count' and 'start_message_id', or None if not found.
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT message_count, start_message_id FROM channel_memory_state WHERE channel_id = ?",
                    (channel_id,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "message_count": int(row["message_count"]),
                        "start_message_id": int(row["start_message_id"])
                    }
                return None
        except Exception as e:
            await func.report_error(e, f"get_channel_memory_state failed for channel {channel_id}")
            return None

    async def update_channel_memory_state(self, channel_id: int, message_count: int, start_message_id: int) -> None:
        """Update the memory state for a specific channel.
        
        Args:
            channel_id (int): The channel ID to update state for.
            message_count (int): The new message count.
            start_message_id (int): The start message ID.
        """
        try:
            with self.db.get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO channel_memory_state
                    (channel_id, message_count, start_message_id)
                    VALUES (?, ?, ?)
                    """,
                    (channel_id, message_count, start_message_id)
                )
                conn.commit()
        except Exception as e:
            await func.report_error(e, f"update_channel_memory_state failed for channel {channel_id}")