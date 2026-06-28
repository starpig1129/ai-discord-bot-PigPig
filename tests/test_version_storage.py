"""Tests for GuildVersionStorage and guild_version_seen schema."""
import sqlite3
import sys
import types
import time
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Stub addons.logging before importing schema
import addons.settings  # noqa: F401 — pre-cache real settings (from conftest pattern)

# Pre-install cogs.memory package chain so schema/version_storage can be imported
# without triggering the full cogs.__init__ dependency tree.
for _pkg, _path in [
    ("cogs", "cogs"),
    ("cogs.memory", "cogs/memory"),
    ("cogs.memory.db", "cogs/memory/db"),
]:
    if _pkg not in sys.modules:
        _mod = types.ModuleType(_pkg)
        _mod.__path__ = [str(project_root / _path)]
        sys.modules[_pkg] = _mod

_fake_exc = types.ModuleType("cogs.memory.exceptions")
class _DatabaseError(Exception): pass
_fake_exc.DatabaseError = _DatabaseError
sys.modules.setdefault("cogs.memory.exceptions", _fake_exc)


class _DummyLogger:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def debug(self, *a, **kw): pass

import addons.logging as _al
_orig_get_logger = _al.get_logger
_al.get_logger = lambda **kwargs: _DummyLogger()


def _in_memory_conn() -> sqlite3.Connection:
    return sqlite3.connect(":memory:")


def test_create_tables_creates_guild_version_seen():
    """create_tables must create the guild_version_seen table."""
    from cogs.memory.db.schema import create_tables
    conn = _in_memory_conn()
    create_tables(conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='guild_version_seen'"
    )
    assert cursor.fetchone() is not None, "guild_version_seen table was not created"
    conn.close()


def test_guild_version_seen_has_correct_columns():
    """guild_version_seen must have guild_id, seen_version, seen_at columns."""
    from cogs.memory.db.schema import create_tables
    conn = _in_memory_conn()
    create_tables(conn)
    cursor = conn.execute("PRAGMA table_info(guild_version_seen)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "guild_id" in columns
    assert "seen_version" in columns
    assert "seen_at" in columns
    conn.close()


class TestGuildVersionStorage:
    """Integration tests using an in-memory SQLite database."""

    def setup_method(self):
        from cogs.memory.db.schema import create_tables
        self.conn = sqlite3.connect(":memory:")
        create_tables(self.conn)
        # Patch DatabaseConnection to return our in-memory conn
        import cogs.memory.db.version_storage as vs_mod
        self._patcher = patch.object(
            vs_mod.GuildVersionStorage, "_open_connection",
            return_value=self.conn,
        )
        self._patcher.start()
        from cogs.memory.db.version_storage import GuildVersionStorage
        self.storage = GuildVersionStorage(":memory:")

    def teardown_method(self):
        self._patcher.stop()
        self.conn.close()

    def test_get_seen_version_returns_none_for_unknown_guild(self):
        result = self.storage.get_seen_version("guild_xyz")
        assert result is None

    def test_set_and_get_seen_version_roundtrip(self):
        self.storage.set_seen_version("guild_abc", "v3.2.0")
        result = self.storage.get_seen_version("guild_abc")
        assert result == "v3.2.0"

    def test_set_seen_version_updates_existing_record(self):
        self.storage.set_seen_version("guild_abc", "v3.1.0")
        self.storage.set_seen_version("guild_abc", "v3.2.0")
        result = self.storage.get_seen_version("guild_abc")
        assert result == "v3.2.0"

    def test_set_seen_version_stores_current_timestamp(self):
        before = time.time()
        self.storage.set_seen_version("guild_time", "v1.0.0")
        after = time.time()
        # Read seen_at directly
        row = self.conn.execute(
            "SELECT seen_at FROM guild_version_seen WHERE guild_id=?", ("guild_time",)
        ).fetchone()
        assert row is not None
        assert before <= row[0] <= after

    def test_multiple_guilds_are_independent(self):
        self.storage.set_seen_version("guild_1", "v3.2.0")
        self.storage.set_seen_version("guild_2", "v3.1.0")
        assert self.storage.get_seen_version("guild_1") == "v3.2.0"
        assert self.storage.get_seen_version("guild_2") == "v3.1.0"
