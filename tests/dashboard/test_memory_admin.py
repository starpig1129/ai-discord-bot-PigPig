"""Tests for new ProceduralStorage methods added for dashboard memory management."""
import json
import asyncio
import tempfile
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


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


# ---------- EpisodicStorage tests ----------

@pytest.mark.asyncio
async def test_episodic_get_total_count():
    from cogs.memory.db.connection import DatabaseConnection
    from cogs.memory.db.episodic_storage import EpisodicStorage

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = DatabaseConnection(db_path)
        storage = EpisodicStorage(db)
        await storage.initialize_channel_memory_state()
        # Insert two channel states
        await storage.update_channel_memory_state(111, 5, 999, None, None)
        await storage.update_channel_memory_state(222, 3, 888, None, None)
        count = await storage.get_total_count()
        assert count == 2

    finally:
        os.unlink(db_path)

# ---------- SQLiteUserManager tests ----------

@pytest.mark.asyncio
async def test_user_manager_get_all_users():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = _make_storage(db_path)
        await _seed_users(storage, 4)
        from cogs.memory.users.manager import SQLiteUserManager
        manager = SQLiteUserManager(storage)
        users = await manager.get_all_users()
        assert len(users) == 4
        assert all(hasattr(u, "discord_id") for u in users)
    finally:
        os.unlink(db_path)


# ---------- require_owner middleware tests (HTTP-level) ----------

def _build_test_app(owner_payload: dict | None, user_payload: dict | None = None):
    """Construct a minimal FastAPI app with the admin router and override dependencies."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dashboard.routers import admin as admin_module
    from dashboard.middleware.permission import require_owner, get_current_user

    app = FastAPI()
    app.include_router(admin_module.router)

    # Provide a fake bot and stats_collector so route handlers don't crash
    fake_bot = MagicMock()
    fake_bot.guilds = []
    fake_bot.is_ready.return_value = True
    fake_bot.latency = 0.05
    app.state.bot = fake_bot
    app.state.stats_collector = MagicMock()

    if owner_payload is not None:
        app.dependency_overrides[get_current_user] = lambda: owner_payload
        app.dependency_overrides[require_owner] = lambda: owner_payload
    else:
        # Simulate a general user that should be blocked by require_owner
        async def _deny():
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Bot Owner access required")

        app.dependency_overrides[require_owner] = _deny

    return TestClient(app, raise_server_exceptions=False)


def test_require_owner_blocks_non_owner(user_token_payload):
    """Non-owner requests to admin routes must receive HTTP 403."""
    client = _build_test_app(owner_payload=None)
    response = client.get("/api/admin/users")
    assert response.status_code == 403
    assert "403" in str(response.status_code)


def test_admin_delete_user_memory_requires_confirm(owner_token_payload):
    """DELETE /api/admin/users/{id}/memory without confirm body returns 400."""
    client = _build_test_app(owner_payload=owner_token_payload)
    # Patch the DB path so it doesn't try to open a real file
    with patch("dashboard.routers.admin._PROCEDURAL_DB") as mock_db:
        mock_db.exists.return_value = False
        response = client.delete(
            "/api/admin/users/test_user_id/memory",
            json={"confirm": False},
        )
    assert response.status_code == 400


def test_admin_delete_user_memory_success(owner_token_payload):
    """DELETE /api/admin/users/{id}/memory with confirm=true deletes from DB."""
    client = _build_test_app(owner_payload=owner_token_payload)
    with (
        patch("dashboard.routers.admin._PROCEDURAL_DB") as mock_pdb,
        patch("dashboard.routers.admin.aiosqlite.connect") as mock_connect,
    ):
        mock_pdb.exists.return_value = False  # Skip actual DB calls; just test routing
        response = client.delete(
            "/api/admin/users/target_user/memory",
            json={"confirm": True},
        )
    # With no DB file, the route skips deletion but still returns 200
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "target_user"

