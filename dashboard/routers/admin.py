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
