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
import aiosqlite
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
_EPISODIC_DB = Path(ROOT_DIR) / "data" / "memory" / "episodic.db"
_PROCEDURAL_DB = Path(ROOT_DIR) / "data" / "memory" / "procedural.db"

from addons.settings import memory_config
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue


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

# Modules that cannot be edited by server admins (from ProtectedPromptManager)
_PROTECTED_MODULES: frozenset[str] = frozenset({
    "output_format",
    "input_parsing",
    "memory_system",
    "information_handling",
    "error_handling",
    "reminders",
})

_CUSTOMIZABLE_MODULES: frozenset[str] = frozenset({
    "identity",
    "response_principles",
    "interaction",
    "professional_personality",
})


def _load_yaml_config() -> dict[str, Any]:
    """Load and return the raw YAML prompt config dict."""
    try:
        if not _PROMPT_YAML.exists():
            return {}
        with open(_PROMPT_YAML, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        log.warning(f"Failed to load prompt YAML: {exc}")
        return {}


def _read_base_prompt_yaml() -> str:
    """Assemble the human-readable base prompt from the YAML config.

    Reads ``configs/prompt/message_agent.yaml`` and concatenates the
    ``content`` fields of each non-base module in default order so the
    dashboard can display it as a read-only reference.

    Returns:
        Combined prompt string (best-effort; empty string on error).
    """
    try:
        cfg = _load_yaml_config()
        composition: dict[str, Any] = cfg.get("composition", {})
        module_order: list[str] = composition.get("module_order", [
            m for m in cfg.keys() if m not in ("metadata", "base", "composition")
        ])

        parts: list[str] = []
        base = cfg.get("base", {})
        if base.get("core_instruction"):
            parts.append(base["core_instruction"].strip())

        for mod_name in module_order:
            if mod_name in ("base", "metadata", "composition"):
                continue
            mod = cfg.get(mod_name)
            if isinstance(mod, dict) and mod.get("content"):
                parts.append(mod["content"].strip())

        return "\n\n".join(parts)
    except Exception as exc:
        log.warning(f"Failed to assemble base prompt YAML: {exc}")
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


# ── Modular Prompt Endpoints ───────────────────────────────────────────────

@router.get("/{guild_id}/prompt/modules")
async def list_prompt_modules(
    guild_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return all prompt modules with their base content and any custom overrides.

    Protected modules are marked as read-only; customizable modules include
    any server-level custom content stored in ``channel_configs``.

    Args:
        guild_id: The target Discord guild ID.
        user: Authenticated user payload.

    Returns:
        JSON with module list, each entry including protection status and content.
    """
    require_guild_access(guild_id, user)

    yaml_cfg = _load_yaml_config()
    guild_cfg = _read_guild_config(guild_id)
    sp = guild_cfg.get("system_prompts", {})
    sp_enabled: bool = sp.get("enabled", False)
    custom_modules: dict[str, Any] = sp.get("modules", {})

    composition: dict[str, Any] = yaml_cfg.get("composition", {})
    module_order: list[str] = composition.get("module_order", [
        m for m in yaml_cfg if m not in ("metadata", "base", "composition", "conditions", "language_replacements")
    ])

    modules: list[dict[str, Any]] = []
    for mod_name in module_order:
        mod_data = yaml_cfg.get(mod_name)
        if not isinstance(mod_data, dict):
            continue

        base_content: str = mod_data.get("content", "").strip()
        description: str = mod_data.get("description", "")
        is_protected: bool = mod_name in _PROTECTED_MODULES
        custom_content: str | None = custom_modules.get(mod_name)

        modules.append({
            "name": mod_name,
            "description": description,
            "protected": is_protected,
            "base_content": base_content,
            "custom_content": custom_content,
            "is_customized": custom_content is not None,
        })

    return JSONResponse({
        "guild_id": guild_id,
        "sp_enabled": sp_enabled,
        "modules": modules,
        "module_order": module_order,
    })


@router.put("/{guild_id}/prompt/modules/{module_name}")
async def update_prompt_module(
    guild_id: str,
    module_name: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Update a single customizable prompt module for a guild.

    Accepts either ``custom_content`` (new text) or ``reset: true`` to revert
    the module to its YAML base. Protected modules cannot be modified.

    Accepted body fields:
        custom_content (str | None): New override text for this module.
        reset (bool): If true, removes any custom override.

    Args:
        guild_id: The target Discord guild ID.
        module_name: The prompt module to update (must be customizable).
        request: FastAPI request.
        user: Authenticated user payload.

    Returns:
        JSON confirmation.

    Raises:
        HTTPException 403: If the module is protected.
        HTTPException 400: If the module name is unknown.
    """
    require_guild_access(guild_id, user)

    if module_name in _PROTECTED_MODULES:
        raise HTTPException(
            status_code=403,
            detail=f"Module '{module_name}' is protected and cannot be modified.",
        )

    yaml_cfg = _load_yaml_config()
    if module_name not in yaml_cfg:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown module '{module_name}'.",
        )

    body: dict[str, Any] = await request.json()
    guild_cfg = _read_guild_config(guild_id)
    sp = guild_cfg.setdefault("system_prompts", {
        "enabled": True,
        "server_level": {},
        "modules": {},
        "channels": {},
        "permissions": {"allowed_roles": [], "allowed_users": [], "manage_server_prompts": []},
    })
    modules_store: dict[str, Any] = sp.setdefault("modules", {})

    if body.get("reset"):
        modules_store.pop(module_name, None)
        log.info(f"Guild {guild_id} module '{module_name}' reset to base by {user.get('sub')}")
    elif "custom_content" in body:
        modules_store[module_name] = str(body["custom_content"])
        log.info(f"Guild {guild_id} module '{module_name}' customized by {user.get('sub')}")

    # Also update sp_enabled if provided
    if "sp_enabled" in body:
        sp["enabled"] = bool(body["sp_enabled"])

    _write_guild_config(guild_id, guild_cfg)
    return JSONResponse({"detail": f"Module '{module_name}' updated."})


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


@router.get("/{guild_id}/channels/{channel_id}/memory")
async def get_channel_memory(
    guild_id: str,
    channel_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return the memory (episodic summary + knowledge + fragments) for a specific channel."""
    require_guild_access(guild_id, user)

    summary = None
    knowledge = None
    fragments = []

    # 1. Fetch episodic summary
    if _EPISODIC_DB.exists():
        try:
            async with aiosqlite.connect(str(_EPISODIC_DB)) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT last_summary_text FROM channel_memory_state WHERE channel_id = ?",
                    (channel_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    summary = row["last_summary_text"] if row else None
        except Exception as exc:
            log.error(f"Episodic summary read failed for {channel_id}: {exc}")

    # 2. Fetch consolidated knowledge
    if _PROCEDURAL_DB.exists():
        try:
            async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT content FROM knowledge WHERE target_type = 'channel' AND target_id = ?",
                    (channel_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    knowledge = row["content"] if row else None
        except Exception as exc:
            log.error(f"Channel knowledge read failed for {channel_id}: {exc}")

    # 3. Fetch episodic fragments from Qdrant
    if memory_config.enabled and memory_config.vector_store_type == "qdrant":
        try:
            # We initialize client here; in a production app, this would be a shared dependency.
            client = QdrantClient(
                url=memory_config.qdrant_url, 
                api_key=memory_config.qdrant_api_key
            )
            
            # Use scroll to get points matching the channel_id in metadata
            # Note: channel_id in Qdrant metadata is stored as a string
            points, _ = client.scroll(
                collection_name=memory_config.qdrant_collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="metadata.channel_id", match=MatchValue(value=str(channel_id)))
                    ]
                ),
                limit=50,
                with_payload=True,
                with_vectors=False
            )
            
            for p in points:
                payload = p.payload or {}
                metadata = payload.get("metadata", {})
                fragments.append({
                    "id": metadata.get("fragment_id", str(p.id)),
                    "content": metadata.get("summary", payload.get("page_content", "")),
                    "timestamp": metadata.get("end_timestamp") or metadata.get("timestamp"),
                })
            
            # Sort by timestamp descending (newest first)
            fragments.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)
            
        except Exception as exc:
            log.error(f"Qdrant fragments read failed for {channel_id}: {exc}")

    return JSONResponse({
        "channel_id": channel_id,
        "summary": summary,
        "knowledge": knowledge,
        "fragments": fragments
    })





@router.get("/{guild_id}/channels/{channel_id}/prompt/modules")
async def list_channel_prompt_modules(
    guild_id: str,
    channel_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Return prompt modules for a specific channel.

    The base_content for a channel module is the server's custom content (if any),
    otherwise the YAML base.

    Args:
        guild_id: The target Discord guild ID.
        channel_id: The target Discord channel ID.
        user: Authenticated user payload.

    Returns:
        JSON with module list and the effective channel enabled status.
    """
    require_guild_access(guild_id, user)

    yaml_cfg = _load_yaml_config()
    guild_cfg = _read_guild_config(guild_id)
    sp = guild_cfg.get("system_prompts", {})
    server_modules: dict[str, Any] = sp.get("modules", {})
    channels: dict[str, Any] = sp.get("channels", {})
    ch_cfg: dict[str, Any] = channels.get(channel_id, {})
    ch_enabled: bool = ch_cfg.get("enabled", False)
    channel_modules: dict[str, Any] = ch_cfg.get("modules", {})

    composition: dict[str, Any] = yaml_cfg.get("composition", {})
    module_order: list[str] = composition.get("module_order", [
        m for m in yaml_cfg if m not in ("metadata", "base", "composition", "conditions", "language_replacements")
    ])

    modules: list[dict[str, Any]] = []
    for mod_name in module_order:
        mod_data = yaml_cfg.get(mod_name)
        if not isinstance(mod_data, dict):
            continue

        description: str = mod_data.get("description", "")
        is_protected: bool = mod_name in _PROTECTED_MODULES
        
        yaml_base: str = mod_data.get("content", "").strip()
        server_custom: str | None = server_modules.get(mod_name)
        
        # Base content for a channel is the server's override, or the YAML default if no override exists
        effective_base: str = server_custom if server_custom is not None else yaml_base
        channel_custom: str | None = channel_modules.get(mod_name)

        modules.append({
            "name": mod_name,
            "description": description,
            "protected": is_protected,
            "base_content": effective_base,
            "custom_content": channel_custom,
            "is_customized": channel_custom is not None,
        })

    return JSONResponse({
        "channel_id": channel_id,
        "enabled": ch_enabled,
        "modules": modules,
        "module_order": module_order,
    })


@router.put("/{guild_id}/channels/{channel_id}/prompt/modules/{module_name}")
async def update_channel_prompt_module(
    guild_id: str,
    channel_id: str,
    module_name: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Update a single customizable prompt module for a channel.

    Args:
        guild_id: The target Discord guild ID.
        channel_id: The Discord channel ID.
        module_name: The prompt module to update.
        request: FastAPI request.
        user: Authenticated user payload.

    Returns:
        JSON confirmation.
    """
    require_guild_access(guild_id, user)

    if module_name in _PROTECTED_MODULES:
        raise HTTPException(
            status_code=403,
            detail=f"Module '{module_name}' is protected and cannot be modified.",
        )

    yaml_cfg = _load_yaml_config()
    if module_name not in yaml_cfg:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown module '{module_name}'.",
        )

    body: dict[str, Any] = await request.json()
    cfg = _read_guild_config(guild_id)
    sp = cfg.setdefault("system_prompts", {
        "enabled": True,
        "server_level": {},
        "modules": {},
        "channels": {},
        "permissions": {"allowed_roles": [], "allowed_users": [], "manage_server_prompts": []},
    })
    channels = sp.setdefault("channels", {})
    ch_cfg = channels.setdefault(channel_id, {})
    ch_modules = ch_cfg.setdefault("modules", {})

    if body.get("reset"):
        ch_modules.pop(module_name, None)
    elif "custom_content" in body:
        ch_modules[module_name] = str(body["custom_content"])

    _write_guild_config(guild_id, cfg)
    log.info(f"Guild {guild_id} channel {channel_id} module '{module_name}' updated by {user.get('sub')}")
    return JSONResponse({"detail": f"Module '{module_name}' updated"})


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
        return JSONResponse(data)
    except Exception as e:
        log.error(f"Guild stats error for {guild_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
