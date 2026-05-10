"""Tests for new ProceduralStorage methods added for dashboard memory management."""
import json
import asyncio
import tempfile
import os
import pytest
from unittest.mock import MagicMock, patch


# ---------- helpers ----------

def _make_storage(db_path: str):
    """Build a real ProceduralStorage backed by a temp SQLite file."""
    from cogs.memory.db.connection import DatabaseConnection
    from cogs.memory.db.procedural_storage import ProceduralStorage
    db = DatabaseConnection(db_path)
    return ProceduralStorage(db)


async def _seed_users(storage, count: int = 3):
    """Insert `count` test users via update_user_data."""
    for i in range(count):
        await storage.update_user_data(
            discord_id=f"user_{i}",
            discord_name=f"TestUser{i}",
            procedural_memory=f"memory_{i}",
            user_background=f"bg_{i}",
            display_names=[f"nick_{i}"],
        )


# ---------- ProceduralStorage tests ----------

@pytest.mark.asyncio
async def test_get_all_users_returns_list():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = _make_storage(db_path)
        await _seed_users(storage, 3)
        users = await storage.get_all_users()
        assert isinstance(users, list)
        assert len(users) == 3
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_get_users_count_returns_int():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = _make_storage(db_path)
        await _seed_users(storage, 5)
        count = await storage.get_users_count()
        assert count == 5
    finally:
        os.unlink(db_path)
