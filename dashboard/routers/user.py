"""General user API routes for the dashboard.

Provides self-service endpoints for any authenticated Discord user.
All endpoints strictly scope data access to the requesting user's own records.

Endpoints:
    GET    /api/user/stats                  — Personal usage statistics
    GET    /api/user/memory/procedural      — Personal procedural memory
    GET    /api/user/memory/episodic        — Personal episodic memory snippets
    DELETE /api/user/memory                 — Delete all personal memory (GDPR)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from addons.logging import get_logger
from dashboard.middleware.permission import get_current_user
from function import ROOT_DIR

log = get_logger(server_id="Bot", source=__name__)
router = APIRouter(prefix="/api/user", tags=["user"])

_PROCEDURAL_DB = Path(ROOT_DIR) / "data" / "memory" / "procedural.db"
_EPISODIC_DB   = Path(ROOT_DIR) / "data" / "memory" / "episodic.db"


# ── Personal Statistics ───────────────────────────────────────────────

@router.get("/stats")
async def user_stats(
    request: Request,
    period: str = "30d",
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return personal usage statistics for the authenticated user.

    Args:
        request: FastAPI request (used to access stats collector).
        period: Time window — "7d", "30d", or "90d".
        user: Authenticated user payload (JWT).

    Returns:
        JSON with total messages, commands, and per-guild breakdown.
    """
    user_id: str = user["sub"]
    stats = request.app.state.stats_collector

    try:
        data = await stats.get_user_stats(user_id, period)
    except Exception as exc:
        log.warning(f"User stats query failed for {user_id}: {exc}")
        data = {
            "user_id": user_id,
            "period": period,
            "total_messages": 0,
            "total_commands": 0,
            "guild_breakdown": [],
        }

    # Enrich guild breakdown with names from bot state
    bot = request.app.state.bot
    for entry in data.get("guild_breakdown", []):
        guild = bot.get_guild(int(entry["guild_id"]))
        entry["guild_name"] = guild.name if guild else entry["guild_id"]

    return JSONResponse(data)


# ── Procedural Memory ─────────────────────────────────────────────────

@router.get("/memory/procedural")
async def get_procedural_memory(
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return the authenticated user's procedural memory (preferences).

    The procedural memory is stored in the ``users`` table as
    a text blob; ``user_background`` captures long-term context.

    Args:
        user: Authenticated user payload (JWT).

    Returns:
        JSON with discord_id, discord_name, procedural_memory, and
        user_background fields.
    """
    user_id: str = user["sub"]

    if not _PROCEDURAL_DB.exists():
        return JSONResponse({
            "user_id": user_id,
            "procedural_memory": None,
            "user_background": None,
            "display_names": [],
        })

    try:
        async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT discord_name, display_names, procedural_memory, user_background "
                "FROM users WHERE discord_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
    except Exception as exc:
        log.error(f"Procedural memory read failed for {user_id}: {exc}")
        raise HTTPException(status_code=503, detail="Memory database temporarily unavailable")

    if row is None:
        return JSONResponse({
            "user_id": user_id,
            "procedural_memory": None,
            "user_background": None,
            "display_names": [],
        })

    display_names: list[str] = []
    try:
        display_names = json.loads(row["display_names"] or "[]")
    except (json.JSONDecodeError, TypeError):
        pass

    return JSONResponse({
        "user_id": user_id,
        "discord_name": row["discord_name"],
        "display_names": display_names,
        "procedural_memory": row["procedural_memory"],
        "user_background": row["user_background"],
    })


# ── Episodic Memory ───────────────────────────────────────────────────

@router.get("/memory/episodic")
async def get_episodic_memory(
    user: dict[str, Any] = Depends(get_current_user),
    guild_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    """Return paginated episodic memory entries for the authenticated user.

    Uses the ``user_stats`` table which records per-user per-guild
    activity metrics. Optionally filters by guild.

    Args:
        user: Authenticated user payload (JWT).
        guild_id: Optional guild filter.
        limit: Maximum records to return (max 100).
        offset: Pagination offset.

    Returns:
        JSON with episodic memory records and pagination info.
    """
    user_id: str = user["sub"]
    limit = min(limit, 100)

    if not _PROCEDURAL_DB.exists():
        return JSONResponse({"user_id": user_id, "records": [], "total": 0})

    try:
        async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
            db.row_factory = aiosqlite.Row

            if guild_id:
                cursor = await db.execute(
                    "SELECT guild_id, total_messages, active_hours, top_channels, "
                    "streak_days, last_active_at, first_message_at "
                    "FROM user_stats WHERE user_id = ? AND guild_id = ? LIMIT ? OFFSET ?",
                    (user_id, guild_id, limit, offset),
                )
                count_cursor = await db.execute(
                    "SELECT COUNT(*) FROM user_stats WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
            else:
                cursor = await db.execute(
                    "SELECT guild_id, total_messages, active_hours, top_channels, "
                    "streak_days, last_active_at, first_message_at "
                    "FROM user_stats WHERE user_id = ? ORDER BY total_messages DESC LIMIT ? OFFSET ?",
                    (user_id, limit, offset),
                )
                count_cursor = await db.execute(
                    "SELECT COUNT(*) FROM user_stats WHERE user_id = ?",
                    (user_id,),
                )

            rows = await cursor.fetchall()
            total = (await count_cursor.fetchone())[0]

    except Exception as exc:
        log.error(f"Episodic memory read failed for {user_id}: {exc}")
        raise HTTPException(status_code=503, detail="Memory database temporarily unavailable")

    # Enrichment: Fetch episodic memory summaries if episodic db exists
    channel_memories = {}
    if _EPISODIC_DB.exists():
        try:
            async with aiosqlite.connect(str(_EPISODIC_DB)) as edb:
                edb.row_factory = aiosqlite.Row
                # Collect all top channel IDs across guilds
                all_channel_ids = set()
                for srow in rows:
                    try:
                        tc = json.loads(srow["top_channels"] or "{}")
                        all_channel_ids.update(tc.keys())
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
            log.warning(f"Failed to fetch episodic enrichment for user {user_id}: {e}")

    records = []
    for row in rows:
        try:
            tc = json.loads(row["top_channels"] or "{}")
        except (json.JSONDecodeError, TypeError):
            tc = {}
        
        mems = {cid: channel_memories[cid] for cid in tc.keys() if cid in channel_memories}
        
        record: dict[str, Any] = {
            "guild_id": row["guild_id"],
            "total_messages": row["total_messages"],
            "streak_days": row["streak_days"],
            "last_active_at": row["last_active_at"],
            "first_message_at": row["first_message_at"],
            "channel_memories": mems
        }
        try:
            record["active_hours"] = json.loads(row["active_hours"] or "{}")
        except (json.JSONDecodeError, TypeError):
            record["active_hours"] = {}
        try:
            record["top_channels"] = tc
        except:
            record["top_channels"] = {}
        records.append(record)

    return JSONResponse({
        "user_id": user_id,
        "records": records,
        "total": total,
        "limit": limit,
        "offset": offset,
    })


# ── Per-Guild Episodic Deletion ───────────────────────────────────────

@router.delete("/memory/episodic/{guild_id}")
async def delete_episodic_by_guild(
    guild_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Delete the authenticated user's episodic memory for a specific guild.

    Removes only the ``user_stats`` row matching (user_id, guild_id).
    Does not affect procedural memory or other guilds.

    Args:
        guild_id: Discord guild ID to delete episodic memory for.
        user: Authenticated user payload (JWT).

    Returns:
        JSON confirming deletion.
    """
    user_id: str = user["sub"]

    if not _PROCEDURAL_DB.exists():
        raise HTTPException(status_code=404, detail="Memory database not found")

    try:
        async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
            cursor = await db.execute(
                "DELETE FROM user_stats WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            )
            await db.commit()
            deleted = cursor.rowcount
    except Exception as exc:
        log.error(f"delete_episodic_by_guild failed for {user_id}/{guild_id}: {exc}")
        raise HTTPException(status_code=503, detail="Memory database temporarily unavailable")

    if deleted == 0:
        raise HTTPException(status_code=404, detail="No episodic memory found for this guild")

    log.info(f"Deleted episodic memory for user {user_id} in guild {guild_id}")
    return JSONResponse({
        "detail": "Episodic memory deleted for guild",
        "user_id": user_id,
        "guild_id": guild_id,
    })


# ── GDPR Delete ───────────────────────────────────────────────────────

@router.delete("/memory")
async def delete_user_memory(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Delete all memory data for the authenticated user (GDPR right-to-erasure).

    Removes records from:
        - ``users`` table (procedural memory, background)
        - ``user_stats`` table (activity statistics)
        - Personal stats in the stats collector database

    This operation is irreversible. The request body must contain
    ``{"confirm": true}`` as a safety gate.

    Args:
        request: FastAPI request.
        user: Authenticated user payload (JWT).

    Returns:
        JSON with deletion confirmation and row counts.

    Raises:
        HTTPException: 400 if confirmation is missing.
        HTTPException: 503 if database operations fail.
    """
    body: dict[str, Any] = await request.json()
    if not body.get("confirm"):
        raise HTTPException(
            status_code=400,
            detail="Deletion requires {'confirm': true} in request body",
        )

    user_id: str = user["sub"]
    deleted: dict[str, int] = {}

    # Delete from procedural memory DB
    if _PROCEDURAL_DB.exists():
        try:
            async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
                cursor = await db.execute(
                    "DELETE FROM users WHERE discord_id = ?", (user_id,)
                )
                deleted["procedural_users"] = cursor.rowcount
                cursor = await db.execute(
                    "DELETE FROM user_stats WHERE user_id = ?", (user_id,)
                )
                deleted["user_stats"] = cursor.rowcount
                await db.commit()
        except Exception as exc:
            log.error(f"Failed to delete procedural memory for {user_id}: {exc}")
            raise HTTPException(
                status_code=503, detail="Failed to delete memory data"
            )

    # Delete from stats DB
    stats_db = Path(ROOT_DIR) / "data" / "stats" / "stats.db"
    if stats_db.exists():
        try:
            async with aiosqlite.connect(str(stats_db)) as db:
                cursor = await db.execute(
                    "DELETE FROM message_events WHERE user_id = ?", (user_id,)
                )
                deleted["message_events"] = cursor.rowcount
                cursor = await db.execute(
                    "DELETE FROM command_events WHERE user_id = ?", (user_id,)
                )
                deleted["command_events"] = cursor.rowcount
                await db.commit()
        except Exception as exc:
            log.warning(f"Failed to delete stats data for {user_id}: {exc}")
            # Non-fatal: memory DB deletion succeeded

    log.info(f"GDPR deletion completed for user {user_id}: {deleted}")
    return JSONResponse({
        "detail": "All personal memory data deleted",
        "user_id": user_id,
        "deleted_rows": deleted,
    })
