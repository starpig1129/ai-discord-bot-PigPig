"""Statistics data collector backed by SQLite (aiosqlite).

Records message events, LLM call events, and command usage into
``data/stats/stats.db``.  Provides aggregation queries for the
dashboard statistics endpoints.
"""

import os
import time
from typing import Any, Optional
from datetime import datetime, timedelta

import aiosqlite

from addons.logging import get_logger
from function import ROOT_DIR

log = get_logger(server_id="Bot", source=__name__)

_DB_PATH = os.path.join(ROOT_DIR, "data", "stats", "stats.db")
_PROCEDURAL_DB = os.path.join(ROOT_DIR, "data", "memory", "procedural.db")

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


def _period_to_days(period: str) -> int:
    """Convert a period string like '7d', '30d', '90d' to number of days."""
    mapping = {"7d": 7, "30d": 30, "90d": 90, "1d": 1, "all": 365}
    return mapping.get(period, 30)


def _fill_missing_days(daily_data: list[dict], days: int) -> list[dict]:
    """Ensure every day in the period has an entry (filled with 0 if missing)."""
    end_date = datetime.now()
    dates = [(end_date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    dates.reverse()

    data_map = {item["date"]: item["count"] for item in daily_data}
    return [{"date": d, "count": data_map.get(d, 0)} for d in dates]


class StatsCollector:
    """Async statistics collector writing to and reading from SQLite."""

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

    async def record_message(self, guild_id: str, user_id: str, channel_id: str, timestamp: Optional[float] = None) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO message_events (guild_id, user_id, channel_id, timestamp) VALUES (?, ?, ?, ?)",
                (guild_id, user_id, channel_id, timestamp or time.time()),
            )
            await db.commit()

    async def bulk_record_messages(self, records: list[tuple[str, str, str, float]]) -> None:
        """Record multiple message events in a single transaction.
        
        Args:
            records: List of (guild_id, user_id, channel_id, timestamp)
        """
        if not records:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.executemany(
                "INSERT INTO message_events (guild_id, user_id, channel_id, timestamp) VALUES (?, ?, ?, ?)",
                records,
            )
            await db.commit()

    async def record_llm_call(self, guild_id: str, model_name: str, duration_ms: float, success: bool = True, timestamp: Optional[float] = None) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO llm_call_events (guild_id, model_name, timestamp, duration_ms, success) VALUES (?, ?, ?, ?, ?)",
                (guild_id, model_name, timestamp or time.time(), duration_ms, int(success)),
            )
            await db.commit()

    async def record_command(self, guild_id: str, user_id: str, command_name: str, timestamp: Optional[float] = None) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO command_events (guild_id, user_id, command_name, timestamp) VALUES (?, ?, ?, ?)",
                (guild_id, user_id, command_name, timestamp or time.time()),
            )
            await db.commit()

    # ── Query methods ─────────────────────────────────────────────────

    async def get_global_stats(self, period: str = "30d") -> dict[str, Any]:
        days = _period_to_days(period)
        cutoff = time.time() - (days * 86400)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute("SELECT COUNT(*) as cnt FROM message_events WHERE timestamp >= ?", (cutoff,))
            total_messages = (await cursor.fetchone())["cnt"]

            cursor = await db.execute(
                "SELECT COUNT(*) as cnt, SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors, AVG(duration_ms) as avg_ms "
                "FROM llm_call_events WHERE timestamp >= ?", (cutoff,)
            )
            row = await cursor.fetchone()
            total_llm = row["cnt"] or 0
            total_errors = row["errors"] or 0
            avg_ms = round(row["avg_ms"], 2) if row["avg_ms"] else 0.0
            error_rate = round(total_errors / total_llm * 100, 2) if total_llm > 0 else 0.0

            cursor = await db.execute(
                "SELECT date(timestamp, 'unixepoch', 'localtime') as day, COUNT(*) as cnt "
                "FROM message_events WHERE timestamp >= ? GROUP BY day ORDER BY day", (cutoff,)
            )
            daily = [{"date": r["day"], "count": r["cnt"]} async for r in cursor]
            daily = _fill_missing_days(daily, days)

            cursor = await db.execute("SELECT COUNT(*) as cnt FROM command_events WHERE timestamp >= ?", (cutoff,))
            total_commands = (await cursor.fetchone())["cnt"]

        accurate_total = await self._get_accurate_total()
        
        return {
            "period": period,
            "total_messages": accurate_total if period == "all" else total_messages,
            "total_llm_calls": total_llm,
            "total_commands": total_commands,
            "error_rate": error_rate,
            "avg_response_ms": avg_ms,
            "daily_messages": daily,
            "accurate_total_messages": accurate_total,
        }

    async def get_model_stats(self, period: str = "30d") -> dict[str, Any]:
        days = _period_to_days(period)
        cutoff = time.time() - (days * 86400)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT model_name, COUNT(*) as calls, AVG(duration_ms) as avg_ms, "
                "SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors "
                "FROM llm_call_events WHERE timestamp >= ? GROUP BY model_name ORDER BY calls DESC", (cutoff,)
            )
            models = []
            async for row in cursor:
                models.append({
                    "model": row["model_name"],
                    "calls": row["calls"],
                    "avg_response_ms": round(row["avg_ms"], 2) if row["avg_ms"] else 0.0,
                    "error_rate": round(row["errors"] / row["calls"] * 100, 2) if row["calls"] > 0 else 0.0,
                    "errors": row["errors"] or 0,
                })
        return {"period": period, "models": models}

    async def get_guild_stats(self, guild_id: str, period: str = "30d") -> dict[str, Any]:
        days = _period_to_days(period)
        cutoff = time.time() - (days * 86400)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute("SELECT COUNT(*) as cnt FROM message_events WHERE guild_id = ? AND timestamp >= ?", (guild_id, cutoff))
            total_messages = (await cursor.fetchone())["cnt"]

            cursor = await db.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM message_events WHERE guild_id = ? AND timestamp >= ?", (guild_id, cutoff))
            active_users = (await cursor.fetchone())["cnt"]

            cursor = await db.execute("SELECT COUNT(*) as cnt, AVG(duration_ms) as avg_ms FROM llm_call_events WHERE guild_id = ? AND timestamp >= ?", (guild_id, cutoff))
            row = await cursor.fetchone()
            llm_calls = row["cnt"] or 0
            avg_ms = round(row["avg_ms"], 2) if row["avg_ms"] else 0.0

            cursor = await db.execute(
                "SELECT date(timestamp, 'unixepoch', 'localtime') as day, COUNT(*) as cnt "
                "FROM message_events WHERE guild_id = ? AND timestamp >= ? GROUP BY day ORDER BY day", (guild_id, cutoff)
            )
            daily = [{"date": r["day"], "count": r["cnt"]} async for r in cursor]
            daily = _fill_missing_days(daily, days)

        accurate_total = await self._get_accurate_total(guild_id)

        return {
            "guild_id": guild_id,
            "period": period,
            "total_messages": accurate_total if period == "all" else total_messages,
            "active_users": active_users,
            "llm_calls": llm_calls,
            "avg_response_ms": avg_ms,
            "daily_messages": daily,
            "accurate_total_messages": accurate_total,
        }

    async def _get_accurate_total(self, guild_id: Optional[str] = None) -> int:
        """Get accurate message count from procedural.db."""
        if not os.path.exists(_PROCEDURAL_DB):
            return 0
        try:
            async with aiosqlite.connect(_PROCEDURAL_DB) as db:
                if guild_id:
                    async with db.execute("SELECT SUM(total_messages) FROM user_stats WHERE guild_id = ?", (guild_id,)) as cursor:
                        row = await cursor.fetchone()
                        return row[0] if row and row[0] else 0
                else:
                    async with db.execute("SELECT SUM(total_messages) FROM user_stats") as cursor:
                        row = await cursor.fetchone()
                        return row[0] if row and row[0] else 0
        except Exception as e:
            log.warning(f"Failed to fetch accurate total: {e}")
            return 0

    async def _get_user_accurate_total(self, user_id: str) -> int:
        """Get accurate message count for a specific user from procedural.db."""
        if not os.path.exists(_PROCEDURAL_DB):
            return 0
        try:
            async with aiosqlite.connect(_PROCEDURAL_DB) as db:
                async with db.execute("SELECT SUM(total_messages) FROM user_stats WHERE user_id = ?", (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row and row[0] else 0
        except Exception as e:
            log.warning(f"Failed to fetch user accurate total: {e}")
            return 0

    async def get_user_stats(self, user_id: str, period: str = "30d") -> dict[str, Any]:
        days = _period_to_days(period)
        cutoff = time.time() - (days * 86400)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT COUNT(*) as cnt FROM message_events WHERE user_id = ? AND timestamp >= ?", (user_id, cutoff))
            total_messages = (await cursor.fetchone())["cnt"]

            cursor = await db.execute("SELECT COUNT(*) as cnt FROM command_events WHERE user_id = ? AND timestamp >= ?", (user_id, cutoff))
            total_commands = (await cursor.fetchone())["cnt"]

            cursor = await db.execute(
                "SELECT guild_id, COUNT(*) as cnt FROM message_events WHERE user_id = ? AND timestamp >= ? GROUP BY guild_id ORDER BY cnt DESC", (user_id, cutoff)
            )
            guilds = [{"guild_id": r["guild_id"], "messages": r["cnt"]} async for r in cursor]

            cursor = await db.execute(
                "SELECT channel_id, guild_id, COUNT(*) as cnt FROM message_events WHERE user_id = ? AND timestamp >= ? GROUP BY channel_id ORDER BY cnt DESC LIMIT 10", (user_id, cutoff)
            )
            channels = [{"channel_id": r["channel_id"], "guild_id": r["guild_id"], "messages": r["cnt"]} async for r in cursor]

        accurate_total = await self._get_user_accurate_total(user_id)

        return {
            "user_id": user_id,
            "period": period,
            "total_messages": accurate_total if period == "all" else total_messages,
            "total_commands": total_commands,
            "guild_breakdown": guilds,
            "channel_breakdown": channels,
            "accurate_total_messages": accurate_total,
        }
