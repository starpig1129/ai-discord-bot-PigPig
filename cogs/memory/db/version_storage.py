"""Per-guild version tracking storage.

Stores which bot version each guild has already seen, so the
version-announcement feature fires exactly once per version per guild.
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional, Union

from addons.logging import get_logger
from cogs.memory.db import schema

logger = get_logger(server_id="system", source=__name__)


class GuildVersionStorage:
    """SQLite-backed store for per-guild seen-version tracking.

    Uses an isolated SQLite connection so it works regardless of whether
    the memory sub-system is enabled.
    """

    def __init__(self, db_path: Union[str, Path]) -> None:
        """Initialize and ensure the required table exists.

        Args:
            db_path: Path to the SQLite database file, or ":memory:" for tests.
        """
        self.db_path = Path(db_path) if db_path != ":memory:" else Path(":memory:")
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_table()

    def _open_connection(self) -> sqlite3.Connection:
        """Open (or reuse) the SQLite connection.

        Returns:
            An open sqlite3.Connection.
        """
        if self._conn is None:
            path_str = str(self.db_path)
            if path_str != ":memory:":
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path_str, check_same_thread=False)
        return self._conn

    def _ensure_table(self) -> None:
        """Create the guild_version_seen table if it does not exist."""
        conn = self._open_connection()
        schema.create_tables(conn)
        conn.commit()

    def get_seen_version(self, guild_id: str) -> Optional[str]:
        """Return the last seen bot version for a guild, or None if not recorded.

        Args:
            guild_id: Discord guild ID as a string.

        Returns:
            Version string (e.g. "v3.2.0") or None.
        """
        try:
            conn = self._open_connection()
            row = conn.execute(
                "SELECT seen_version FROM guild_version_seen WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
            return row[0] if row else None
        except Exception as exc:
            logger.error(f"get_seen_version failed for guild {guild_id}: {exc}")
            return None

    def set_seen_version(self, guild_id: str, version: str) -> None:
        """Record that guild_id has seen the given bot version.

        Args:
            guild_id: Discord guild ID as a string.
            version: Bot version string (e.g. "v3.2.0").

        Raises:
            sqlite3.Error: On database write failure.
        """
        conn = self._open_connection()
        conn.execute(
            """
            INSERT INTO guild_version_seen (guild_id, seen_version, seen_at)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                seen_version = excluded.seen_version,
                seen_at      = excluded.seen_at
            """,
            (guild_id, version, time.time()),
        )
        conn.commit()
        logger.info(f"Guild {guild_id} marked as seen version {version}")
