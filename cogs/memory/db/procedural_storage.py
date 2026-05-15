"""ProceduralStorage: handles users table and configuration storage.

This module extracts the procedural (user) related SQL logic from the previous
sqlite_storage implementation so responsibilities are separated.
All error reporting uses func.report_error per project rules.
"""
from __future__ import annotations

import json
import sqlite3
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..users.models import UserInfo
from .connection import DatabaseConnection
from function import func
from addons.logging import get_logger
logger = get_logger(server_id="system", source=__name__)


class ProceduralStorage:
    """Handles users table and config storage."""

    def __init__(self, db: DatabaseConnection) -> None:
        self.db = db
        self._user_cache: Dict[str, UserInfo] = {}
        self._cache_size_limit = 1000
        self.logger = logger

    async def get_user_info(self, discord_id: str) -> Optional[UserInfo]:
        if discord_id in self._user_cache:
            return self._user_cache[discord_id]

        try:
            return await asyncio.to_thread(self._get_user_info_sync, discord_id)
        except Exception as e:
            await func.report_error(e, f"get_user_info failed (user: {discord_id})")
            return None

    def _get_user_info_sync(self, discord_id: str) -> Optional[UserInfo]:
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT discord_id, discord_name, display_names,
                       procedural_memory, user_background, created_at
                FROM users
                WHERE discord_id = ?
                """,
                (discord_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            display_names = []
            if row["display_names"]:
                try:
                    display_names = json.loads(row["display_names"])
                    if not isinstance(display_names, list):
                        display_names = [str(display_names)]
                except Exception:
                    display_names = [row["display_names"]]

            created_at = None
            if row["created_at"]:
                try:
                    created_at = datetime.fromisoformat(row["created_at"])
                except Exception:
                    try:
                        created_at = datetime.fromtimestamp(float(row["created_at"]))
                    except Exception:
                        created_at = None

            user_info = UserInfo(
                discord_id=str(row["discord_id"]),
                discord_name=row["discord_name"] or "",
                display_names=display_names,
                procedural_memory=row["procedural_memory"],
                user_background=row["user_background"],
                created_at=created_at,
            )

            self._update_cache(discord_id, user_info)
            return user_info

    async def update_user_data(
        self,
        discord_id: str,
        discord_name: str,
        procedural_memory: Optional[str] = None,
        user_background: Optional[str] = None,
        display_names: Optional[List[str]] = None,
        nickname: Optional[str] = None,
    ) -> bool:
        try:
            return await asyncio.to_thread(
                self._update_user_data_sync,
                discord_id, discord_name, procedural_memory, user_background, display_names, nickname
            )
        except sqlite3.IntegrityError as ie:
            await func.report_error(ie, f"Integrity error updating user {discord_id}")
            return False
        except Exception as e:
            await func.report_error(e, f"update_user_data failed (user: {discord_id})")
            return False

    def _update_user_data_sync(
        self,
        discord_id: str,
        discord_name: str,
        procedural_memory: Optional[str] = None,
        user_background: Optional[str] = None,
        display_names: Optional[List[str]] = None,
        nickname: Optional[str] = None,
    ) -> bool:
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT discord_id, discord_name, display_names, procedural_memory, user_background FROM users WHERE discord_id = ?",
                (discord_id,)
            )
            row = cursor.fetchone()
            exists = row is not None

            existing_display_names = []
            if row and row["display_names"]:
                try:
                    existing_display_names = json.loads(row["display_names"])
                except Exception:
                    existing_display_names = [row["display_names"]]

            new_display_names = set(existing_display_names)
            if display_names:
                new_display_names.update(display_names)
            if discord_name:
                new_display_names.add(discord_name)
            if nickname:
                new_display_names.add(nickname)

            if exists:
                # If a field is None, it means "keep existing value".
                # If a field is empty string, it means "clear/set to empty".
                # COALESCE in SQL doesn't distinguish between None and missing if we pass NULL.
                # So we handle it here.
                final_name = discord_name if discord_name is not None else row["discord_name"]
                final_pm = procedural_memory if procedural_memory is not None else row["procedural_memory"]
                final_bg = user_background if user_background is not None else row["user_background"]

                conn.execute(
                    """
                    UPDATE users
                    SET discord_name = ?,
                        display_names = ?,
                        procedural_memory = ?,
                        user_background = ?
                    WHERE discord_id = ?
                    """,
                    (
                        final_name,
                        json.dumps(list(new_display_names), ensure_ascii=False),
                        final_pm,
                        final_bg,
                        discord_id,
                    ),
                )
            else:
                now_iso = datetime.utcnow().isoformat()
                conn.execute(
                    """
                    INSERT INTO users (discord_id, discord_name, display_names, procedural_memory, user_background, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        discord_id,
                        discord_name or "",
                        json.dumps(list(new_display_names), ensure_ascii=False),
                        procedural_memory,
                        user_background,
                        now_iso,
                    ),
                )
            conn.commit()

            if discord_id in self._user_cache:
                del self._user_cache[discord_id]
            return True

    async def delete_user_data(self, discord_id: str) -> bool:
        try:
            return await asyncio.to_thread(self._delete_user_data_sync, discord_id)
        except Exception as e:
            await func.report_error(e, f"delete_user_data failed (user: {discord_id})")
            return False

    def _delete_user_data_sync(self, discord_id: str) -> bool:
        with self.db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM users WHERE discord_id = ?", (discord_id,))
            conn.commit()
            deleted = cursor.rowcount > 0

            if deleted and discord_id in self._user_cache:
                del self._user_cache[discord_id]
            return deleted

    async def update_user_activity(self, discord_id: str, discord_name: str, nickname: Optional[str] = None) -> bool:
        try:
            return await asyncio.to_thread(self._update_user_activity_sync, discord_id, discord_name, nickname)
        except Exception as e:
            await func.report_error(e, f"update_user_activity failed (user: {discord_id})")
            return False

    def _update_user_activity_sync(self, discord_id: str, discord_name: str, nickname: Optional[str] = None) -> bool:
        with self.db.get_connection() as conn:
            cursor = conn.execute("SELECT display_names FROM users WHERE discord_id = ?", (discord_id,))
            row = cursor.fetchone()
            if row:
                existing_display_names = []
                if row["display_names"]:
                    try:
                        existing_display_names = json.loads(row["display_names"])
                    except Exception:
                        existing_display_names = [row["display_names"]]
                changed = False
                if discord_name and discord_name not in existing_display_names:
                    existing_display_names.append(discord_name)
                    changed = True
                if nickname and nickname not in existing_display_names:
                    existing_display_names.append(nickname)
                    changed = True
                
                if changed:
                    conn.execute(
                        """
                        UPDATE users
                        SET discord_name = COALESCE(?, discord_name),
                            display_names = COALESCE(?, display_names)
                        WHERE discord_id = ?
                        """,
                        (discord_name or None, json.dumps(existing_display_names, ensure_ascii=False), discord_id),
                    )
            else:
                now_iso = datetime.utcnow().isoformat()
                names = set()
                if discord_name: names.add(discord_name)
                if nickname: names.add(nickname)
                display_names = list(names)
                conn.execute(
                    """
                    INSERT INTO users (discord_id, discord_name, display_names, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (discord_id, discord_name or "", json.dumps(display_names, ensure_ascii=False), now_iso),
                )
            conn.commit()

            if discord_id in self._user_cache:
                del self._user_cache[discord_id]
            return True

    async def get_all_users(self, limit: int = 500, offset: int = 0) -> List[UserInfo]:
        """Return all users ordered by creation date (newest first)."""
        try:
            return await asyncio.to_thread(self._get_all_users_sync, limit, offset)
        except Exception as e:
            await func.report_error(e, "get_all_users failed")
            return []

    def _get_all_users_sync(self, limit: int, offset: int) -> List[UserInfo]:
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT discord_id, discord_name, display_names,
                       procedural_memory, user_background, created_at
                FROM users
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = cursor.fetchall()

        users: List[UserInfo] = []
        for row in rows:
            display_names: List[str] = []
            if row["display_names"]:
                try:
                    parsed = json.loads(row["display_names"])
                    display_names = parsed if isinstance(parsed, list) else [str(parsed)]
                except Exception:
                    display_names = [row["display_names"]]

            created_at = None
            if row["created_at"]:
                try:
                    created_at = datetime.fromisoformat(row["created_at"])
                except Exception:
                    try:
                        created_at = datetime.fromtimestamp(float(row["created_at"]))
                    except Exception:
                        created_at = None

            users.append(UserInfo(
                discord_id=str(row["discord_id"]),
                discord_name=row["discord_name"] or "",
                display_names=display_names,
                procedural_memory=row["procedural_memory"],
                user_background=row["user_background"],
                created_at=created_at,
            ))
        return users

    async def get_users_count(self) -> int:
        """Return total number of users in the database."""
        try:
            return await asyncio.to_thread(self._get_users_count_sync)
        except Exception as e:
            await func.report_error(e, "get_users_count failed")
            return 0

    def _get_users_count_sync(self) -> int:
        with self.db.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as count FROM users")
            row = cursor.fetchone()
            return int(row["count"]) if row else 0

    async def get_config(self, key: str) -> Optional[str]:
        try:
            return await asyncio.to_thread(self._get_config_sync, key)
        except Exception as e:
            await func.report_error(e, f"get_config failed (key: {key})")
            return None

    def _get_config_sync(self, key: str) -> Optional[str]:
        with self.db.get_connection() as conn:
            cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None

    async def set_config(self, key: str, value: str) -> None:
        try:
            await asyncio.to_thread(self._set_config_sync, key, value)
        except Exception as e:
            await func.report_error(e, f"set_config failed (key: {key})")

    def _set_config_sync(self, key: str, value: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    def _update_cache(self, user_id: str, user_info: UserInfo) -> None:
        try:
            if len(self._user_cache) >= self._cache_size_limit:
                oldest = next(iter(self._user_cache))
                del self._user_cache[oldest]
            self._user_cache[user_id] = user_info
        except Exception as e:
            # This runs in a thread — cannot await or create tasks
            import logging as _logging
            _logging.getLogger(__name__).exception("cache update failed: %s", e)