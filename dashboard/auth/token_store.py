"""Persistent refresh-token store backed by SQLite.

Replaces the in-memory dict so tokens survive bot restarts.
"""
from __future__ import annotations

import time
from pathlib import Path

import aiosqlite

from addons.logging import get_logger
from function import ROOT_DIR

log = get_logger(server_id="Bot", source=__name__)

_DB_PATH = Path(ROOT_DIR) / "data" / "auth" / "tokens.db"


async def initialize() -> None:
    """Create the tokens table if it doesn't exist."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token      TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                exp        REAL NOT NULL
            )
            """
        )
        await db.commit()


async def store(token: str, user_id: str, exp: float) -> None:
    """Persist a new refresh token.

    Args:
        token: Refresh token string.
        user_id: Discord user ID.
        exp: Expiration timestamp (Unix time).

    Raises:
        Logs errors instead of raising to maintain fire-and-forget semantics.
    """
    try:
        async with aiosqlite.connect(str(_DB_PATH)) as db:
            await db.execute(
                "INSERT OR REPLACE INTO refresh_tokens (token, user_id, exp) VALUES (?, ?, ?)",
                (token, user_id, exp),
            )
            await db.commit()
    except Exception as exc:
        log.error(f"Failed to persist refresh token for user {user_id}: {exc}")


async def lookup(token: str) -> str | None:
    """Return user_id for a valid non-expired token, or None.

    Args:
        token: Refresh token string to look up.

    Returns:
        User ID if token is valid and not expired, None otherwise.
    """
    try:
        async with aiosqlite.connect(str(_DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT user_id, exp FROM refresh_tokens WHERE token = ?", (token,)
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        if time.time() > row["exp"]:
            await revoke(token)
            return None
        return row["user_id"]
    except Exception as exc:
        log.error(f"Failed to lookup refresh token: {exc}")
        return None


async def revoke(token: str) -> None:
    """Delete a single refresh token.

    Args:
        token: Refresh token string to revoke.

    Raises:
        Logs errors instead of raising to allow graceful degradation.
    """
    try:
        async with aiosqlite.connect(str(_DB_PATH)) as db:
            await db.execute("DELETE FROM refresh_tokens WHERE token = ?", (token,))
            await db.commit()
    except Exception as exc:
        log.error(f"Failed to revoke refresh token: {exc}")


async def cleanup_expired() -> None:
    """Purge all expired tokens from the database.

    Raises:
        Logs errors instead of raising to allow graceful degradation.
    """
    try:
        async with aiosqlite.connect(str(_DB_PATH)) as db:
            await db.execute("DELETE FROM refresh_tokens WHERE exp < ?", (time.time(),))
            await db.commit()
    except Exception as exc:
        log.error(f"Failed to cleanup expired refresh tokens: {exc}")
