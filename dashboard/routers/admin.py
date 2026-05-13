"""Bot Owner admin API routes for the dashboard."""

from __future__ import annotations

import os
import time
import platform
import psutil
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import aiosqlite
from pathlib import Path
from fastapi import Query


from addons.logging import get_logger
from addons.tokens import tokens
from dashboard.middleware.permission import require_owner
from function import ROOT_DIR

log = get_logger(server_id="Bot", source=__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

_START_TIME = time.time()


def _get_bot(request: Request):
    """Retrieve bot instance from app state."""
    return request.app.state.bot


def _get_stats(request: Request):
    """Retrieve stats collector from app state."""
    return request.app.state.stats_collector


# ── Bot Status ────────────────────────────────────────────────────────

@router.get("/status")
async def bot_status(
    request: Request,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Return real-time bot status information."""
    bot = _get_bot(request)
    latency_ms = round(bot.latency * 1000, 2) if bot.latency else 0
    uptime = time.time() - _START_TIME
    process = psutil.Process(os.getpid())
    mem = process.memory_info()

    return JSONResponse({
        "status": "online" if bot.is_ready() else "connecting",
        "latency_ms": latency_ms,
        "uptime_seconds": round(uptime, 1),
        "guilds": len(bot.guilds),
        "users": sum(g.member_count or 0 for g in bot.guilds),
        "memory_mb": round(mem.rss / 1024 / 1024, 1),
        "python_version": platform.python_version(),
        "bot_name": str(bot.user) if bot.user else "Unknown",
        "bot_id": str(bot.user.id) if bot.user else "0",
    })


# ── Guild List ────────────────────────────────────────────────────────

@router.get("/guilds")
async def list_guilds(
    request: Request,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Return all guilds the bot is connected to."""
    bot = _get_bot(request)
    guilds = []
    for g in bot.guilds:
        guilds.append({
            "id": str(g.id),
            "name": g.name,
            "member_count": g.member_count,
            "icon": str(g.icon.url) if g.icon else None,
            "owner_id": str(g.owner_id) if g.owner_id else None,
        })
    return JSONResponse({"guilds": guilds})


# ── Config CRUD ───────────────────────────────────────────────────────

_ALLOWED_CONFIGS = {"base", "llm", "memory", "music"}


def _config_path(file: str) -> str:
    """Resolve config file path from its base name."""
    config_root = os.getenv("CONFIG_ROOT", "configs")
    return os.path.join(ROOT_DIR, config_root, f"{file}.yaml")


@router.get("/config/{file}")
async def read_config(
    file: str,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Read a YAML configuration file."""
    if file not in _ALLOWED_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Unknown config: {file}")
    path = _config_path(file)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Config file not found: {file}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Mask sensitive API keys
    _mask_secrets(data)
    return JSONResponse({"file": file, "config": data})


@router.put("/config/{file}")
async def write_config(
    file: str,
    request: Request,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Write/update a YAML configuration file."""
    if file not in _ALLOWED_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Unknown config: {file}")
    body = await request.json()
    config_data = body.get("config")
    if config_data is None:
        raise HTTPException(status_code=400, detail="Missing 'config' in request body")
    path = _config_path(file)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
    log.info(f"Config '{file}.yaml' updated by user {user.get('sub')}")
    return JSONResponse({"detail": f"{file}.yaml updated successfully"})


def _mask_secrets(data: Any, depth: int = 0) -> None:
    """Recursively mask values that look like API keys."""
    if depth > 10 or not isinstance(data, dict):
        return
    for key, value in data.items():
        if isinstance(value, str) and any(
            kw in key.lower() for kw in ("key", "secret", "token", "password")
        ):
            if len(value) > 8:
                data[key] = value[:4] + "****" + value[-4:]
        elif isinstance(value, dict):
            _mask_secrets(value, depth + 1)


# ── Update Management ────────────────────────────────────────────────

@router.post("/update/check")
async def check_update(
    request: Request,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Check for available version updates."""
    try:
        from addons.update import VersionChecker
        from addons.settings import update_config
        checker = VersionChecker(update_config.github)
        result = await checker.check_for_updates()
        current = checker.get_current_version()
        return JSONResponse({
            "current_version": current,
            "latest_version": result.get("latest_version", current),
            "update_available": result.get("latest_version", current) != current,
            "release_notes": result.get("release_notes", ""),
        })
    except Exception as e:
        log.error(f"Update check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update/execute")
async def execute_update(
    request: Request,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Execute a bot update (requires confirmation)."""
    body = await request.json()
    if not body.get("confirm"):
        raise HTTPException(status_code=400, detail="Confirmation required")
    try:
        from addons.update import VersionChecker
        from addons.settings import update_config
        checker = VersionChecker(update_config.github)
        result = await checker.perform_update()
        return JSONResponse({"detail": "Update initiated", "result": result})
    except Exception as e:
        log.error(f"Update execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── User Management (Bot Owner) ───────────────────────────────────────

_PROCEDURAL_DB = Path(ROOT_DIR) / "data" / "memory" / "procedural.db"
_EPISODIC_DB = Path(ROOT_DIR) / "data" / "memory" / "episodic.db"


@router.get("/users")
async def list_users(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default=""),
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """List all users with procedural memory data (Bot Owner only)."""
    if not _PROCEDURAL_DB.exists():
        return JSONResponse({"users": [], "total": 0})

    try:
        async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
            db.row_factory = aiosqlite.Row
            if search:
                pattern = f"%{search}%"
                cursor = await db.execute(
                    """
                    SELECT discord_id, discord_name, display_names, created_at,
                           CASE WHEN procedural_memory IS NOT NULL THEN 1 ELSE 0 END as has_memory
                    FROM users
                    WHERE discord_name LIKE ? OR display_names LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (pattern, pattern, limit, offset),
                )
                count_cursor = await db.execute(
                    "SELECT COUNT(*) FROM users WHERE discord_name LIKE ? OR display_names LIKE ?",
                    (pattern, pattern),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT discord_id, discord_name, display_names, created_at,
                           CASE WHEN procedural_memory IS NOT NULL THEN 1 ELSE 0 END as has_memory
                    FROM users
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
                count_cursor = await db.execute("SELECT COUNT(*) FROM users")

            rows = await cursor.fetchall()
            total = (await count_cursor.fetchone())[0]

    except Exception as exc:
        log.error(f"list_users failed: {exc}")
        raise HTTPException(status_code=503, detail="Memory database unavailable")

    import json as _json
    users_out = []
    for row in rows:
        display_names = []
        try:
            display_names = _json.loads(row["display_names"] or "[]")
        except Exception:
            pass
        users_out.append({
            "discord_id": row["discord_id"],
            "discord_name": row["discord_name"],
            "display_names": display_names,
            "created_at": row["created_at"],
            "has_memory": bool(row["has_memory"]),
        })

    return JSONResponse({"users": users_out, "total": total, "limit": limit, "offset": offset})


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    request: Request,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Get full memory details for a specific user (Bot Owner only)."""
    if not _PROCEDURAL_DB.exists():
        raise HTTPException(status_code=404, detail="Memory database not found")

    import json as _json
    
    user_row = None
    stats_rows = []
    try:
        async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
            db.row_factory = aiosqlite.Row

            user_cursor = await db.execute(
                "SELECT discord_id, discord_name, display_names, procedural_memory, user_background, created_at "
                "FROM users WHERE discord_id = ?",
                (user_id,),
            )
            user_row = await user_cursor.fetchone()

            stats_cursor = await db.execute(
                "SELECT guild_id, total_messages, streak_days, last_active_at, first_message_at, top_channels "
                "FROM user_stats WHERE user_id = ? ORDER BY total_messages DESC",
                (user_id,),
            )
            stats_rows = await stats_cursor.fetchall()

        # Enrichment: Fetch episodic memory summaries if episodic db exists
        channel_memories = {}
        if _EPISODIC_DB.exists():
            try:
                async with aiosqlite.connect(str(_EPISODIC_DB)) as edb:
                    edb.row_factory = aiosqlite.Row
                    # Resolve name-based top_channels keys to IDs for episodic enrichment
                    bot = request.app.state.bot
                    all_channel_ids = set()
                    
                    for srow in stats_rows:
                        try:
                            tc = _json.loads(srow["top_channels"] or "{}")
                            gid = srow["guild_id"]
                            
                            # Cache guild channel map for resolution
                            guild = bot.get_guild(int(gid))
                            name_map = {}
                            if guild:
                                name_map = {c.name: str(c.id) for c in guild.channels}
                                
                            for key in tc.keys():
                                if key.isdigit():
                                    all_channel_ids.add(key)
                                elif key in name_map:
                                    all_channel_ids.add(name_map[key])
                        except:
                            continue
                    
                    if all_channel_ids:
                        placeholders = ",".join(["?"] * len(all_channel_ids))
                        m_cursor = await edb.execute(
                            f"SELECT channel_id, last_summary_text FROM channel_memory_state WHERE channel_id IN ({placeholders})",
                            list(all_channel_ids)
                        )
                        mrows = await m_cursor.fetchall()
                        for mrow in mrows:
                            channel_memories[str(mrow["channel_id"])] = mrow["last_summary_text"]
            except Exception as e:
                log.warning(f"Failed to fetch episodic enrichment: {e}")

    except Exception as exc:
        log.error(f"get_user_detail failed for {user_id}: {exc}")
        raise HTTPException(status_code=503, detail="Memory database unavailable")

    if user_row is None:
        raise HTTPException(status_code=404, detail="User not found")

    display_names = []
    try:
        display_names = _json.loads(user_row["display_names"] or "[]")
    except Exception:
        pass

    guild_stats = []
    for row in stats_rows:
        # For memories dictionary, handle potential name keys using the same defensive logic
        tc = {}
        try:
            tc = _json.loads(row["top_channels"] or "{}")
        except:
            pass
            
        memories = {}
        bot = request.app.state.bot
        guild = bot.get_guild(int(row["guild_id"]))
        name_map = {c.name: str(c.id) for c in guild.channels} if guild else {}
        
        for key in tc.keys():
            cid = None
            if key.isdigit():
                cid = key
            elif key in name_map:
                cid = name_map[key]
                
            if cid and cid in channel_memories:
                memories[key] = channel_memories[cid]
        
        guild_stats.append({
            "guild_id": row["guild_id"],
            "total_messages": row["total_messages"],
            "streak_days": row["streak_days"],
            "last_active_at": row["last_active_at"],
            "first_message_at": row["first_message_at"],
            "channel_memories": memories
        })

    return JSONResponse({
        "discord_id": user_row["discord_id"],
        "discord_name": user_row["discord_name"],
        "display_names": display_names,
        "procedural_memory": user_row["procedural_memory"],
        "user_background": user_row["user_background"],
        "created_at": user_row["created_at"],
        "guild_stats": guild_stats,
    })


@router.delete("/users/{user_id}/memory")
async def admin_delete_user_memory(
    user_id: str,
    request: Request,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Delete all memory data for a specific user (Bot Owner only)."""
    body: dict = await request.json()
    if not body.get("confirm"):
        raise HTTPException(status_code=400, detail="Requires {'confirm': true}")

    deleted: dict[str, int] = {}
    stats_db = Path(ROOT_DIR) / "data" / "stats" / "stats.db"

    if _PROCEDURAL_DB.exists():
        try:
            async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
                c = await db.execute("DELETE FROM users WHERE discord_id = ?", (user_id,))
                deleted["procedural_users"] = c.rowcount
                c = await db.execute("DELETE FROM user_stats WHERE user_id = ?", (user_id,))
                deleted["user_stats"] = c.rowcount
                await db.commit()
        except Exception as exc:
            log.error(f"admin_delete_user_memory failed for {user_id}: {exc}")
            raise HTTPException(status_code=503, detail="Failed to delete user memory")

    if stats_db.exists():
        try:
            async with aiosqlite.connect(str(stats_db)) as db:
                c = await db.execute("DELETE FROM message_events WHERE user_id = ?", (user_id,))
                deleted["message_events"] = c.rowcount
                c = await db.execute("DELETE FROM command_events WHERE user_id = ?", (user_id,))
                deleted["command_events"] = c.rowcount
                await db.commit()
        except Exception as exc:
            log.warning(f"admin stats deletion failed for {user_id}: {exc}")

    log.info(f"Admin GDPR deletion for user {user_id} by owner: {deleted}")
    return JSONResponse({"detail": "User memory deleted", "user_id": user_id, "deleted_rows": deleted})

