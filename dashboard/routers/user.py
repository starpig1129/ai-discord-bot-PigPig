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

from addons.settings import memory_config
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny


# ── Personal Statistics ───────────────────────────────────────────────

@router.get("/stats")
async def user_stats(
    request: Request,
    period: str = "30d",
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return personal usage statistics for the authenticated user.

    Integrates real-time events from StatsCollector with accurate cumulative
    data from the procedural memory database (which includes historical logs).

    Args:
        request: FastAPI request.
        period: Time window — "7d", "30d", "90d", or "all".
        user: Authenticated user payload (JWT).

    Returns:
        JSON with total messages, commands, and per-guild/channel breakdown.
    """
    user_id: str = user["sub"]
    stats_collector = request.app.state.stats_collector

    # 1. Fetch time-windowed data from StatsCollector (recent trends)
    try:
        data = await stats_collector.get_user_stats(user_id, period)
    except Exception as exc:
        log.warning(f"StatsCollector query failed for {user_id}: {exc}")
        data = {
            "user_id": user_id,
            "period": period,
            "total_messages": 0,
            "total_commands": 0,
            "guild_breakdown": [],
        }

    # 2. Fetch accurate cumulative data from procedural.db
    # This is the "source of truth" for total message counts.
    accurate_total_messages = 0
    channel_list = [] # List of {guild_id, channel_name, messages}

    if _PROCEDURAL_DB.exists():
        try:
            async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT guild_id, total_messages, top_channels FROM user_stats WHERE user_id = ?",
                    (user_id,),
                )
                rows = await cursor.fetchall()
                for row in rows:
                    gid = row["guild_id"]
                    accurate_total_messages += row["total_messages"]
                    try:
                        tc = json.loads(row["top_channels"] or "{}")
                        for cname, count in tc.items():
                            channel_list.append({
                                "guild_id": gid,
                                "channel_name": cname,
                                "messages": count
                            })
                    except:
                        continue
        except Exception as e:
            log.warning(f"Failed to fetch accurate stats from procedural.db: {e}")

    # 3. Merge data
    # If period is "all", we use the accurate total.
    # Otherwise, we keep the StatsCollector's windowed total but provide the accurate one as a reference.
    if period == "all":
        data["total_messages"] = accurate_total_messages
        # For "all", we also need to rebuild guild_breakdown from procedural.db
        # (StatsCollector only has recent guild activity)
        try:
            async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT guild_id, total_messages FROM user_stats WHERE user_id = ? ORDER BY total_messages DESC",
                    (user_id,),
                )
                data["guild_breakdown"] = [
                    {"guild_id": r["guild_id"], "messages": r["total_messages"]}
                    for r in await cursor.fetchall()
                ]
        except:
            pass
    
    # Always include accurate total and channel breakdown
    data["accurate_total_messages"] = accurate_total_messages
    
    # 4. Enrich breakdowns with names from bot state
    bot = request.app.state.bot
    # Guild names enrichment
    for entry in data.get("guild_breakdown", []):
        guild = bot.get_guild(int(entry["guild_id"]))
        entry["guild_name"] = guild.name if guild else entry["guild_id"]
    
    # Channel list enrichment
    for entry in channel_list:
        guild = bot.get_guild(int(entry["guild_id"]))
        entry["guild_name"] = guild.name if guild else entry["guild_id"]
    
    data["channel_breakdown"] = sorted(channel_list, key=lambda x: x["messages"], reverse=True)

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
    request: Request,
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
    bot = request.app.state.bot
    channel_summaries = {}
    
    # Pre-fetch all relevant channel IDs across all guilds for this user
    all_target_channel_ids = set()
    guild_channel_maps = {} # guild_id -> {name: id}

    for row in rows:
        gid = row["guild_id"]
        guild = bot.get_guild(int(gid))
        if not guild:
            continue
            
        # Build mapping for this guild
        name_map = {c.name: str(c.id) for c in guild.channels}
        guild_channel_maps[gid] = name_map
        
        try:
            tc = json.loads(row["top_channels"] or "{}")
            for cname in tc.keys():
                if cname in name_map:
                    all_target_channel_ids.add(name_map[cname])
        except:
            continue

    if _EPISODIC_DB.exists() and all_target_channel_ids:
        try:
            async with aiosqlite.connect(str(_EPISODIC_DB)) as edb:
                edb.row_factory = aiosqlite.Row
                placeholders = ",".join(["?"] * len(all_target_channel_ids))
                m_cursor = await edb.execute(
                    f"SELECT channel_id, last_summary_text FROM channel_memory_state WHERE channel_id IN ({placeholders})",
                    list(all_target_channel_ids)
                )
                mrows = await m_cursor.fetchall()
                for mrow in mrows:
                    channel_summaries[str(mrow["channel_id"])] = mrow["last_summary_text"]
        except Exception as e:
            log.warning(f"Failed to fetch episodic enrichment: {e}")

    records = []
    for row in rows:
        gid = row["guild_id"]
        try:
            tc = json.loads(row["top_channels"] or "{}")
        except (json.JSONDecodeError, TypeError):
            tc = {}
        
        # Build memories dict for this guild's top channels
        mems = {}
        name_map = guild_channel_maps.get(gid, {})
        for cname in tc.keys():
            cid = name_map.get(cname)
            if cid and cid in channel_summaries:
                mems[cname] = channel_summaries[cid]
        
        # Resolve guild name
        guild = bot.get_guild(int(gid))
        guild_name = guild.name if guild else gid
        
        record: dict[str, Any] = {
            "guild_id": gid,
            "guild_name": guild_name,
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

    # Enrichment: Fetch episodic fragments from Qdrant for this user
    fragments = []
    if memory_config.enabled and memory_config.vector_store_type == "qdrant":
        try:
            client = QdrantClient(
                url=memory_config.qdrant_url, 
                api_key=memory_config.qdrant_api_key
            )
            
            # Filter by user_id in metadata.author_ids (Qdrant stores this inside a metadata object in payload)
            points, _ = client.scroll(
                collection_name=memory_config.qdrant_collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="metadata.author_ids", match=MatchAny(any=[str(user_id)]))
                    ]
                ),
                limit=100,
                with_payload=True,
                with_vectors=False
            )
            
            for p in points:
                payload = p.payload or {}
                metadata = payload.get("metadata", {})
                # The payload contains a 'metadata' dict when using LangChain Qdrant
                fragments.append({
                    "id": metadata.get("fragment_id", str(p.id)),
                    "content": metadata.get("summary", payload.get("page_content", "")),
                    "timestamp": metadata.get("end_timestamp") or metadata.get("timestamp"),
                    "guild_id": metadata.get("guild_id"),
                    "channel_id": metadata.get("channel_id"),
                })
            
            fragments.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)
            
        except Exception as exc:
            log.error(f"Qdrant fragments read failed for user {user_id}: {exc}")

    return JSONResponse({
        "user_id": user_id,
        "records": records,
        "fragments": fragments,
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
