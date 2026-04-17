"""KnowledgeStorage: handles guild and channel level knowledge storage.

This module provides persistence for shared interaction knowledge, including
inside jokes, relationships, and special events.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from .connection import DatabaseConnection
from function import func
from addons.logging import get_logger

logger = get_logger(server_id="system", source=__name__)


class KnowledgeStorage:
    """Handles knowledge table storage operations."""

    def __init__(self, db: DatabaseConnection) -> None:
        """Initialize with a DatabaseConnection instance."""
        self.db = db
        self.logger = logger

    async def get_knowledge(self, target_type: str, target_id: str) -> Optional[str]:
        """Retrieve knowledge for a specific scope (guild or channel).

        Args:
            target_type: Either 'guild' or 'channel'.
            target_id: The Discord snowflake ID for the target.

        Returns:
            The stored knowledge content as a string, or None if not found.
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT content
                    FROM knowledge
                    WHERE target_type = ? AND target_id = ?
                    """,
                    (target_type, target_id),
                )
                row = cursor.fetchone()
                return row["content"] if row else None
        except Exception as e:
            await func.report_error(e, f"get_knowledge failed (type: {target_type}, id: {target_id})")
            return None

    async def update_knowledge(self, target_type: str, target_id: str, content: str) -> bool:
        """Update or insert knowledge for a specific scope.

        Args:
            target_type: Either 'guild' or 'channel'.
            target_id: The Discord snowflake ID for the target.
            content: The new structured knowledge text.

        Returns:
            True if successful, False otherwise.
        """
        try:
            now_iso = datetime.utcnow().isoformat()
            with self.db.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO knowledge (target_type, target_id, content, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(target_type, target_id) DO UPDATE SET
                        content = excluded.content,
                        updated_at = excluded.updated_at
                    """,
                    (target_type, target_id, content, now_iso),
                )
                conn.commit()
                return True
        except Exception as e:
            await func.report_error(e, f"update_knowledge failed (type: {target_type}, id: {target_id})")
            return False

    async def delete_knowledge(self, target_type: str, target_id: str) -> bool:
        """Delete knowledge for a specific scope.

        Args:
            target_type: Either 'guild' or 'channel'.
            target_id: The Discord snowflake ID for the target.

        Returns:
            True if something was deleted, False otherwise.
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM knowledge WHERE target_type = ? AND target_id = ?",
                    (target_type, target_id),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            await func.report_error(e, f"delete_knowledge failed (type: {target_type}, id: {target_id})")
            return False
