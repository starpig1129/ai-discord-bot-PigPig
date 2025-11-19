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
        except Exception as e:
            await func.report_error(e, f"get_user_info failed (user: {discord_id})")
            return None

    async def update_user_data(
        self,
        discord_id: str,
        discord_name: str,
        procedural_memory: Optional[str] = None,
        user_background: Optional[str] = None,
        display_names: Optional[List[str]] = None,
    ) -> bool:
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT discord_id, display_names FROM users WHERE discord_id = ?", (discord_id,))
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

                if exists:
                    conn.execute(
                        """
                        UPDATE users
                        SET discord_name = COALESCE(?, discord_name),
                            display_names = COALESCE(?, display_names),
                            procedural_memory = COALESCE(?, procedural_memory),
                            user_background = COALESCE(?, user_background)
                        WHERE discord_id = ?
                        """,
                        (
                            discord_name or None,
                            json.dumps(list(new_display_names), ensure_ascii=False),
                            procedural_memory or None,
                            user_background or None,
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
                            procedural_memory or None,
                            user_background or None,
                            now_iso,
                        ),
                    )
                conn.commit()

                if discord_id in self._user_cache:
                    del self._user_cache[discord_id]
                return True
        except sqlite3.IntegrityError as ie:
            await func.report_error(ie, f"Integrity error updating user {discord_id}")
            return False
        except Exception as e:
            await func.report_error(e, f"update_user_data failed (user: {discord_id})")
            return False

    async def update_user_activity(self, discord_id: str, discord_name: str) -> bool:
        try:
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
                    if discord_name and discord_name not in existing_display_names:
                        existing_display_names.append(discord_name)
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
                    display_names = [discord_name] if discord_name else []
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
        except Exception as e:
            await func.report_error(e, f"update_user_activity failed (user: {discord_id})")
            return False

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

    def _update_cache(self, user_id: str, user_info: UserInfo) -> None:
        try:
            if len(self._user_cache) >= self._cache_size_limit:
                oldest = next(iter(self._user_cache))
                del self._user_cache[oldest]
            self._user_cache[user_id] = user_info
        except Exception as e:
            # avoid awaiting in synchronous helper; spawn a task
            asyncio.create_task(func.report_error(e, "cache update failed"))