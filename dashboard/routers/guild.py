"""Server Admin API routes for the dashboard.

Provides guild-scoped endpoints accessible to Bot Owner or Server Admins
who have administrator permissions on the requested guild.

Endpoints:
    GET  /api/guild/{guild_id}/overview      — Guild summary
    GET  /api/guild/{guild_id}/channels      — Channel config list
    PUT  /api/guild/{guild_id}/channels/{id} — Update channel settings
    GET  /api/guild/{guild_id}/prompt        — System prompt config
    PUT  /api/guild/{guild_id}/prompt        — Update system prompt
    GET  /api/guild/{guild_id}/stats         — Guild-scoped statistics
"""

from __future__ import annotations

import json
import os
import yaml
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from addons.logging import get_logger
from dashboard.middleware.permission import get_current_user, require_guild_access
from function import ROOT_DIR

log = get_logger(server_id="Bot", source=__name__)
router = APIRouter(prefix="/api/guild", tags=["guild"])

_CHANNEL_CONFIG_DIR = Path(ROOT_DIR) / "data" / "channel_configs"


# ── Helpers ───────────────────────────────────────────────────────────

def _read_guild_config(guild_id: str) -> dict[str, Any]:
    """Load channel config JSON for a guild; return empty structure on miss."""
    path = _CHANNEL_CONFIG_DIR / f"{guild_id}.json"
    if not path.exists():
        return {
            "mode": "unrestricted",
            "whitelist": [],
            "blacklist": [],
            "auto_response": {},
            "system_prompts": {
                "enabled": True,
                "server_level": {},
                "channels": {},
                "permissions": {
                    "allowed_roles": [],
                    "allowed_users": [],
                    "manage_server_prompts": [],
                },
            },
            "channel_modes": {},
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_guild_config(guild_id: str, data: dict[str, Any]) -> None:
    """Persist channel config JSON for a guild."""
    _CHANNEL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = _CHANNEL_CONFIG_DIR / f"{guild_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_bot(request: Request):
    """Retrieve bot instance from app state."""
    return request.app.state.bot


def _get_stats(request: Request):
    """Retrieve stats collector from app state."""
    return request.app.state.stats_collector


# ── Guild Overview ────────────────────────────────────────────────────

@router.get("/{guild_id}/overview")
async def guild_overview(
    guild_id: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return high-level overview of a guild.

    Args:
        guild_id: The target Discord guild ID.
        request: FastAPI request (used to access bot state).
        user: Authenticated user payload from JWT.

    Returns:
        JSON with guild name, member count, channel count, and Bot status.
    """
    require_guild_access(guild_id, user)

    bot = _get_bot(request)
    guild = bot.get_guild(int(guild_id))
    if guild is None:
        raise HTTPException(status_code=404, detail="Guild not found")

    cfg = _read_guild_config(guild_id)
    text_channels = [c for c in guild.channels if hasattr(c, "topic")]

    return JSONResponse({
        "id": str(guild.id),
        "name": guild.name,
        "icon": str(guild.icon.url) if guild.icon else None,
        "member_count": guild.member_count,
        "channel_count": len(text_channels),
        "bot_online": bot.is_ready(),
        "mode": cfg.get("mode", "unrestricted"),
        "system_prompt_enabled": cfg.get("system_prompts", {}).get("enabled", False),
    })


# ── Channel Configuration ─────────────────────────────────────────────

@router.get("/{guild_id}/channels")
async def list_channels(
    guild_id: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return all text channels with their current config state.

    Args:
        guild_id: The target Discord guild ID.
        request: FastAPI request.
        user: Authenticated user payload.

    Returns:
        JSON with channel list and per-channel settings.
    """
    require_guild_access(guild_id, user)

    bot = _get_bot(request)
    guild = bot.get_guild(int(guild_id))
    if guild is None:
        raise HTTPException(status_code=404, detail="Guild not found")

    cfg = _read_guild_config(guild_id)
    whitelist: list[str] = cfg.get("whitelist", [])
    blacklist: list[str] = cfg.get("blacklist", [])
    auto_response: dict[str, bool] = cfg.get("auto_response", {})
    channel_modes: dict[str, str] = cfg.get("channel_modes", {})
    guild_mode: str = cfg.get("mode", "unrestricted")

    channels = []
    for ch in sorted(guild.text_channels, key=lambda c: c.position):
        ch_id = str(ch.id)
        channels.append({
            "id": ch_id,
            "name": ch.name,
            "category": ch.category.name if ch.category else None,
            "position": ch.position,
            "guild_mode": guild_mode,
            "in_whitelist": ch_id in whitelist,
            "in_blacklist": ch_id in blacklist,
            "auto_response": auto_response.get(ch_id, False),
            "channel_mode": channel_modes.get(ch_id, "inherit"),
        })

    return JSONResponse({
        "guild_id": guild_id,
        "guild_mode": guild_mode,
        "channels": channels,
    })


@router.put("/{guild_id}/channels/{channel_id}")
async def update_channel(
    guild_id: str,
    channel_id: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Update configuration for a specific channel.

    Accepted body fields (all optional):
        in_whitelist (bool): Add/remove channel from whitelist.
        in_blacklist (bool): Add/remove channel from blacklist.
        auto_response (bool): Enable/disable auto-response.
        channel_mode (str): "inherit" | "story" | "disabled".
        guild_mode (str): Guild-level mode — updates the whole guild setting.

    Args:
        guild_id: The target Discord guild ID.
        channel_id: The Discord channel ID to update.
        request: FastAPI request.
        user: Authenticated user payload.

    Returns:
        JSON confirmation with updated settings.
    """
    require_guild_access(guild_id, user)

    body: dict[str, Any] = await request.json()
    cfg = _read_guild_config(guild_id)

    # Guild-level mode update
    if "guild_mode" in body:
        cfg["mode"] = body["guild_mode"]

    # Per-channel whitelist / blacklist
    whitelist: list[str] = cfg.setdefault("whitelist", [])
    blacklist: list[str] = cfg.setdefault("blacklist", [])

    if "in_whitelist" in body:
        if body["in_whitelist"]:
            if channel_id not in whitelist:
                whitelist.append(channel_id)
            if channel_id in blacklist:
                blacklist.remove(channel_id)
        else:
            if channel_id in whitelist:
                whitelist.remove(channel_id)

    if "in_blacklist" in body:
        if body["in_blacklist"]:
            if channel_id not in blacklist:
                blacklist.append(channel_id)
            if channel_id in whitelist:
                whitelist.remove(channel_id)
        else:
            if channel_id in blacklist:
                blacklist.remove(channel_id)

    # Auto-response toggle
    if "auto_response" in body:
        cfg.setdefault("auto_response", {})[channel_id] = bool(body["auto_response"])

    # Channel-level mode (story / disabled / inherit)
    if "channel_mode" in body:
        cfg.setdefault("channel_modes", {})[channel_id] = body["channel_mode"]

    _write_guild_config(guild_id, cfg)
    log.info(
        f"Guild {guild_id} channel {channel_id} config updated by user {user.get('sub')}"
    )
    return JSONResponse({"detail": "Channel config updated", "channel_id": channel_id})


# ── System Prompt ─────────────────────────────────────────────────────

_PROMPT_YAML = Path(ROOT_DIR) / "configs" / "prompt" / "message_agent.yaml"


def _read_base_prompt_yaml() -> str:
    """Assemble the human-readable base prompt from the YAML config.

    Reads ``configs/prompt/message_agent.yaml`` and concatenates the
    ``content`` fields of each non-base module in default order so the
    dashboard can display it as a read-only reference.

    Returns:
        Combined prompt string (best-effort; empty string on error).
    """
    try:
        if not _PROMPT_YAML.exists():
            return ""
        with open(_PROMPT_YAML, "r", encoding="utf-8") as f:
            cfg: dict[str, Any] = yaml.safe_load(f) or {}

        composition: dict[str, Any] = cfg.get("composition", {})
        module_order: list[str] = composition.get("module_order", [
            m for m in cfg.keys() if m not in ("metadata", "base", "composition")
        ])

        parts: list[str] = []
        # Core instruction from base section
        base = cfg.get("base", {})
        if base.get("core_instruction"):
            parts.append(base["core_instruction"].strip())

        for mod_name in module_order:
            if mod_name in ("base", "metadata", "composition"):
                continue
            mod = cfg.get(mod_name)
            if isinstance(mod, dict):
                content = mod.get("content", "")
                if content:
                    parts.append(content.strip())

        return "\n\n".join(parts)
    except Exception as exc:
        log.warning(f"Failed to read base prompt YAML: {exc}")
        return ""


@router.get("/{guild_id}/prompt/effective")
async def get_effective_prompt(
    guild_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return the currently *effective* system prompt for a guild.

    The effective prompt is composed of:
    1. The YAML base (``configs/prompt/message_agent.yaml``) as a
       read-only reference.
    2. The optional server-level override stored in ``channel_configs``.

    Args:
        guild_id: The target Discord guild ID.
        user: Authenticated user payload.

    Returns:
        JSON with ``base_prompt`` and ``override`` fields.
    """
    require_guild_access(guild_id, user)

    cfg = _read_guild_config(guild_id)
    sp = cfg.get("system_prompts", {})
    server_level: dict[str, Any] = sp.get("server_level", {})

    return JSONResponse({
        "guild_id": guild_id,
        "base_prompt": _read_base_prompt_yaml(),
        "override_enabled": bool(server_level.get("prompt")),
        "override_prompt": server_level.get("prompt", server_level.get("content", "")),
        "override_name": server_level.get("name", ""),
    })


@router.get("/{guild_id}/prompt")
async def get_prompt(
    guild_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return the system prompt configuration for a guild.

    Args:
        guild_id: The target Discord guild ID.
        user: Authenticated user payload.

    Returns:
        JSON with prompt enabled flag and server-level prompt text.
    """
    require_guild_access(guild_id, user)

    cfg = _read_guild_config(guild_id)
    sp = cfg.get("system_prompts", {})
    server_level: dict[str, Any] = sp.get("server_level", {})

    return JSONResponse({
        "guild_id": guild_id,
        "enabled": sp.get("enabled", False),
        # Bot's SystemPromptManager uses key 'prompt' (not 'content')
        "prompt": server_level.get("prompt", server_level.get("content", "")),
        "prompt_name": server_level.get("name", ""),
    })


@router.put("/{guild_id}/prompt")
async def update_prompt(
    guild_id: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Update the server-level system prompt for a guild.

    Accepted body fields:
        enabled (bool): Enable/disable system prompt.
        prompt (str): The new prompt content.
        prompt_name (str): Optional name label for this prompt.

    Args:
        guild_id: The target Discord guild ID.
        request: FastAPI request.
        user: Authenticated user payload.

    Returns:
        JSON confirmation.
    """
    require_guild_access(guild_id, user)

    body: dict[str, Any] = await request.json()
    cfg = _read_guild_config(guild_id)
    sp = cfg.setdefault("system_prompts", {})

    if "enabled" in body:
        sp["enabled"] = bool(body["enabled"])

    server_level = sp.setdefault("server_level", {})
    if "prompt" in body:
        # Write as 'prompt' to match SystemPromptManager.set_server_prompt
        server_level["prompt"] = str(body["prompt"])
    if "prompt_name" in body:
        server_level["name"] = str(body["prompt_name"])

    _write_guild_config(guild_id, cfg)
    log.info(
        f"Guild {guild_id} system prompt updated by user {user.get('sub')}"
    )
    return JSONResponse({"detail": "System prompt updated"})


# ── Channel-level Prompt ──────────────────────────────────────────────

@router.get("/{guild_id}/channels/{channel_id}/prompt")
async def get_channel_prompt(
    guild_id: str,
    channel_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return the system prompt config for a specific channel.

    Args:
        guild_id: The target Discord guild ID.
        channel_id: The Discord channel ID.
        user: Authenticated user payload.

    Returns:
        JSON with channel prompt text and enabled flag.
    """
    require_guild_access(guild_id, user)

    cfg = _read_guild_config(guild_id)
    channels: dict[str, Any] = cfg.get("system_prompts", {}).get("channels", {})
    ch_cfg: dict[str, Any] = channels.get(channel_id, {})

    return JSONResponse({
        "channel_id": channel_id,
        "enabled": ch_cfg.get("enabled", False),
        "prompt": ch_cfg.get("prompt", ""),
    })


@router.put("/{guild_id}/channels/{channel_id}/prompt")
async def update_channel_prompt(
    guild_id: str,
    channel_id: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Update system prompt for a specific channel.

    Accepted body fields:
        enabled (bool): Enable/disable channel-level override.
        prompt (str): The channel-specific prompt content.

    Args:
        guild_id: The target Discord guild ID.
        channel_id: The Discord channel ID.
        request: FastAPI request.
        user: Authenticated user payload.

    Returns:
        JSON confirmation.
    """
    require_guild_access(guild_id, user)

    body: dict[str, Any] = await request.json()
    cfg = _read_guild_config(guild_id)
    sp = cfg.setdefault("system_prompts", {
        "enabled": True,
        "server_level": {},
        "channels": {},
        "permissions": {"allowed_roles": [], "allowed_users": [], "manage_server_prompts": []},
    })
    channels = sp.setdefault("channels", {})
    ch_cfg = channels.setdefault(channel_id, {})

    if "enabled" in body:
        ch_cfg["enabled"] = bool(body["enabled"])
    if "prompt" in body:
        ch_cfg["prompt"] = str(body["prompt"])

    _write_guild_config(guild_id, cfg)
    log.info(f"Guild {guild_id} channel {channel_id} prompt updated by {user.get('sub')}")
    return JSONResponse({"detail": "Channel prompt updated"})


# ── Guild Stats ───────────────────────────────────────────────────────

@router.get("/{guild_id}/stats")
async def guild_stats(
    guild_id: str,
    request: Request,
    period: str = "30d",
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return usage statistics for a specific guild.

    Args:
        guild_id: The target Discord guild ID.
        request: FastAPI request.
        period: Time range — "7d", "30d", or "90d".
        user: Authenticated user payload.

    Returns:
        JSON with guild-scoped message counts, LLM usage, and daily trends.
    """
    require_guild_access(guild_id, user)

    stats = _get_stats(request)
    try:
        data = await stats.get_guild_stats(guild_id, period)
    except Exception as exc:
        log.warning(f"Guild stats query failed for {guild_id}: {exc}")
        data = {
            "total_messages": 0,
            "total_llm_calls": 0,
            "total_commands": 0,
            "active_users": 0,
            "daily_messages": [],
        }

    return JSONResponse({"guild_id": guild_id, "period": period, **data})
