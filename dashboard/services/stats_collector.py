"""Statistics data collector backed by SQLite (aiosqlite).

Records message events, LLM call events, and command usage into
``data/stats/stats.db``.  Provides aggregation queries for the
dashboard statistics endpoints.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import aiosqlite

from addons.logging import get_logger
from function import ROOT_DIR

log = get_logger(server_id="Bot", source=__name__)

_DB_PATH = os.path.join(ROOT_DIR, "data", "stats", "stats.db")

# ── SQL Schemas ───────────────────────────────────────────────────────
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS message_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    TEXT    NOT NULL,
    user_id     TEXT    NOT NULL,
    channel_id  TEXT    NOT NULL,
    timestamp   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_call_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    TEXT    NOT NULL,
    model_name  TEXT    NOT NULL,
    timestamp   REAL    NOT NULL,
    duration_ms REAL    NOT NULL DEFAULT 0,
    success     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS command_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id      TEXT    NOT NULL,
    user_id       TEXT    NOT NULL,
    command_name  TEXT    NOT NULL,
    timestamp     REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_msg_ts    ON message_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_msg_guild ON message_events(guild_id);
CREATE INDEX IF NOT EXISTS idx_llm_ts    ON llm_call_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_cmd_ts    ON command_events(timestamp);
"""


def _period_to_seconds(period: str) -> float:
    """Convert a period string like '7d', '30d', '90d' to seconds.

    Args:
        period: Period string (e.g., "7d", "30d", "90d").

    Returns:
        Number of seconds as float.
    """
    mapping = {"7d": 7, "30d": 30, "90d": 90, "1d": 1}
    days = mapping.get(period, 30)
    return days * 86400.0


class StatsCollector:
    """Async statistics collector writing to and reading from SQLite.

    Attributes:
        _db_path: Absolute path to the SQLite database file.
        _initialized: Whether the schema has been created.
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        """Create database directory and tables if they don't exist."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA_SQL)
            await db.commit()
        self._initialized = True
        log.info(f"Stats database initialized at {self._db_path}")

    # ── Write methods ─────────────────────────────────────────────────

    async def record_message(
        self,
        guild_id: str,
        user_id: str,
        channel_id: str,
    ) -> None:
        """Record a message event.

        Args:
            guild_id: Discord guild ID.
            user_id: Discord user ID.
            channel_id: Discord channel ID.
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO message_events (guild_id, user_id, channel_id, timestamp) VALUES (?, ?, ?, ?)",
                (guild_id, user_id, channel_id, time.time()),
            )
            await db.commit()

    async def record_llm_call(
        self,
        guild_id: str,
        model_name: str,
        duration_ms: float,
        success: bool = True,
    ) -> None:
        """Record an LLM API call event.

        Args:
            guild_id: Discord guild ID.
            model_name: Name/identifier of the LLM model used.
            duration_ms: Call duration in milliseconds.
            success: Whether the call succeeded.
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO llm_call_events (guild_id, model_name, timestamp, duration_ms, success) VALUES (?, ?, ?, ?, ?)",
                (guild_id, model_name, time.time(), duration_ms, int(success)),
            )
            await db.commit()

    async def record_command(
        self,
        guild_id: str,
        user_id: str,
        command_name: str,
    ) -> None:
        """Record a command usage event.

        Args:
            guild_id: Discord guild ID.
            user_id: Discord user ID.
            command_name: Name of the command executed.
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO command_events (guild_id, user_id, command_name, timestamp) VALUES (?, ?, ?, ?)",
                (guild_id, user_id, command_name, time.time()),
            )
            await db.commit()

    # ── Query methods ─────────────────────────────────────────────────

    async def get_global_stats(self, period: str = "30d") -> dict[str, Any]:
        """Get aggregated global statistics.

        Args:
            period: Time window (e.g., "7d", "30d", "90d").

        Returns:
            Dict with total_messages, total_llm_calls, error_rate,
            avg_response_ms, and daily_breakdown.
        """
        cutoff = time.time() - _period_to_seconds(period)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # Total messages
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM message_events WHERE timestamp >= ?",
                (cutoff,),
            )
            row = await cursor.fetchone()
            total_messages = row[0] if row else 0

            # LLM calls
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt, "
                "SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors, "
                "AVG(duration_ms) as avg_ms "
                "FROM llm_call_events WHERE timestamp >= ?",
                (cutoff,),
            )
            row = await cursor.fetchone()
            total_llm = row[0] if row else 0
            total_errors = row[1] if row and row[1] else 0
            avg_ms = round(row[2], 2) if row and row[2] else 0.0
            error_rate = round(total_errors / total_llm * 100, 2) if total_llm > 0 else 0.0

            # Daily message breakdown (last N days)
            cursor = await db.execute(
                "SELECT date(timestamp, 'unixepoch') as day, COUNT(*) as cnt "
                "FROM message_events WHERE timestamp >= ? "
                "GROUP BY day ORDER BY day",
                (cutoff,),
            )
            daily = [{"date": r[0], "count": r[1]} async for r in cursor]

            # Commands
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM command_events WHERE timestamp >= ?",
                (cutoff,),
            )
            row = await cursor.fetchone()
            total_commands = row[0] if row else 0

        return {
            "period": period,
            "total_messages": total_messages,
            "total_llm_calls": total_llm,
            "total_commands": total_commands,
            "error_rate": error_rate,
            "avg_response_ms": avg_ms,
            "daily_messages": daily,
        }

    async def get_model_stats(self, period: str = "30d") -> dict[str, Any]:
        """Get per-model LLM usage and performance statistics.

        Args:
            period: Time window.

        Returns:
            Dict with per-model breakdown and percentiles.
        """
        cutoff = time.time() - _period_to_seconds(period)

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT model_name, COUNT(*) as calls, "
                "AVG(duration_ms) as avg_ms, "
                "SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors "
                "FROM llm_call_events WHERE timestamp >= ? "
                "GROUP BY model_name ORDER BY calls DESC",
                (cutoff,),
            )
            models = []
            async for row in cursor:
                calls = row[1]
                errors = row[3] if row[3] else 0
                models.append({
                    "model": row[0],
                    "calls": calls,
                    "avg_response_ms": round(row[2], 2) if row[2] else 0.0,
                    "error_rate": round(errors / calls * 100, 2) if calls > 0 else 0.0,
                    "errors": errors,
                })

        return {"period": period, "models": models}

    async def get_guild_stats(
        self, guild_id: str, period: str = "30d"
    ) -> dict[str, Any]:
        """Get statistics for a specific guild.

        Args:
            guild_id: Discord guild ID.
            period: Time window.

        Returns:
            Dict with guild-specific message, LLM, and command stats.
        """
        cutoff = time.time() - _period_to_seconds(period)

        async with aiosqlite.connect(self._db_path) as db:
            # Messages
            cursor = await db.execute(
                "SELECT COUNT(*) FROM message_events WHERE guild_id = ? AND timestamp >= ?",
                (guild_id, cutoff),
            )
            total_messages = (await cursor.fetchone())[0]

            # Active users
            cursor = await db.execute(
                "SELECT COUNT(DISTINCT user_id) FROM message_events WHERE guild_id = ? AND timestamp >= ?",
                (guild_id, cutoff),
            )
            active_users = (await cursor.fetchone())[0]

            # LLM calls
            cursor = await db.execute(
                "SELECT COUNT(*), AVG(duration_ms) FROM llm_call_events WHERE guild_id = ? AND timestamp >= ?",
                (guild_id, cutoff),
            )
            row = await cursor.fetchone()
            llm_calls = row[0] if row else 0
            avg_ms = round(row[1], 2) if row and row[1] else 0.0

            # Daily breakdown
            cursor = await db.execute(
                "SELECT date(timestamp, 'unixepoch') as day, COUNT(*) as cnt "
                "FROM message_events WHERE guild_id = ? AND timestamp >= ? "
                "GROUP BY day ORDER BY day",
                (guild_id, cutoff),
            )
            daily = [{"date": r[0], "count": r[1]} async for r in cursor]

        return {
            "guild_id": guild_id,
            "period": period,
            "total_messages": total_messages,
            "active_users": active_users,
            "llm_calls": llm_calls,
            "avg_response_ms": avg_ms,
            "daily_messages": daily,
        }

    async def get_user_stats(
        self, user_id: str, period: str = "30d"
    ) -> dict[str, Any]:
        """Get statistics for a specific user.

        Args:
            user_id: Discord user ID.
            period: Time window.

        Returns:
            Dict with user-specific message and command counts.
        """
        cutoff = time.time() - _period_to_seconds(period)

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM message_events WHERE user_id = ? AND timestamp >= ?",
                (user_id, cutoff),
            )
            total_messages = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT COUNT(*) FROM command_events WHERE user_id = ? AND timestamp >= ?",
                (user_id, cutoff),
            )
            total_commands = (await cursor.fetchone())[0]

            # Per-guild breakdown
            cursor = await db.execute(
                "SELECT guild_id, COUNT(*) as cnt FROM message_events "
                "WHERE user_id = ? AND timestamp >= ? GROUP BY guild_id ORDER BY cnt DESC",
                (user_id, cutoff),
            )
            guilds = [{"guild_id": r[0], "messages": r[1]} async for r in cursor]

        return {
            "user_id": user_id,
            "period": period,
            "total_messages": total_messages,
            "total_commands": total_commands,
            "guild_breakdown": guilds,
        }
