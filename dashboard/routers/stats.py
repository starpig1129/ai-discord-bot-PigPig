"""Statistics API routes for the dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse

from addons.logging import get_logger
from dashboard.middleware.permission import require_owner, get_current_user

import aiosqlite
from pathlib import Path
from function import ROOT_DIR

log = get_logger(server_id="Bot", source=__name__)
router = APIRouter(prefix="/api", tags=["stats"])

_PROCEDURAL_DB = Path(ROOT_DIR) / "data" / "memory" / "procedural.db"


def _get_stats(request: Request):
    """Retrieve stats collector from app state."""
    return request.app.state.stats_collector


def _get_bot(request: Request):
    """Retrieve bot instance from app state."""
    return request.app.state.bot


@router.get("/admin/stats/global")
async def global_stats(
    request: Request,
    period: str = Query(default="30d"),
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Global aggregated statistics (Bot Owner only)."""
    stats = _get_stats(request)
    data = await stats.get_global_stats(period)
    return JSONResponse(data)


@router.get("/admin/stats/models")
async def model_stats(
    request: Request,
    period: str = Query(default="30d"),
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Per-model LLM usage and performance stats (Bot Owner only)."""
    stats = _get_stats(request)
    data = await stats.get_model_stats(period)
    return JSONResponse(data)


@router.get("/admin/stats/memory")
async def memory_stats(
    request: Request,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Memory system statistics (Bot Owner only)."""
    bot = _get_bot(request)
    result = {"procedural_users": 0, "episodic_total": 0, "vector_collections": 0}
    try:
        if hasattr(bot, "user_manager") and bot.user_manager:
            users = await bot.user_manager.get_all_users()
            result["procedural_users"] = len(users) if users else 0
    except Exception:
        pass
    try:
        if hasattr(bot, "episodic_storage") and bot.episodic_storage:
            result["episodic_total"] = await bot.episodic_storage.get_total_count()
    except Exception:
        pass
    try:
        if hasattr(bot, "vector_manager") and bot.vector_manager:
            info = await bot.vector_manager.get_collection_info()
            result["vector_collections"] = info.get("count", 0) if info else 0
    except Exception:
        pass
    return JSONResponse(result)



