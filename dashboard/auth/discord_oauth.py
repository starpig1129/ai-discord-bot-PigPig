"""Discord OAuth2 authentication routes for the dashboard.

Implements the full OAuth2 authorization code flow:
login → Discord authorize → callback → JWT issuance.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

from addons.logging import get_logger
from addons.tokens import tokens
from addons.settings import base_config
from dashboard.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_access_token,
    verify_refresh_token,
    revoke_refresh_token,
    verify_refresh_token_async,
    revoke_refresh_token_async,
)

log = get_logger(server_id="Bot", source=__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Discord OAuth2 endpoints ──────────────────────────────────────────
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
SCOPES = "identify guilds"


def _get_redirect_uri(request: Request) -> str:
    """Build the OAuth2 redirect URI from the incoming request.

    Args:
        request: The current FastAPI request.

    Returns:
        Absolute callback URL string.
    """
    # Use request base URL, but ensure localhost is used instead of 127.0.0.1 
    # to match the strict exact-string whitelist in the Discord Developer Portal.
    base = str(request.base_url).rstrip("/")
    base = base.replace("127.0.0.1", "localhost")
    return f"{base}/auth/discord/callback"


def _get_bot(request: Request):
    """Retrieve the bot instance attached to the FastAPI app state.

    Args:
        request: The current FastAPI request.

    Returns:
        The PigPig bot instance.
    """
    return request.app.state.bot


# ── Routes ────────────────────────────────────────────────────────────

@router.get("/discord/login")
async def discord_login(request: Request) -> RedirectResponse:
    """Redirect the user to the Discord OAuth2 authorization page.

    Returns:
        302 redirect to Discord authorize URL.
    """
    params = {
        "client_id": tokens.client_id,
        "redirect_uri": _get_redirect_uri(request),
        "response_type": "code",
        "scope": SCOPES,
    }
    url = f"{DISCORD_AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/discord/callback")
async def discord_callback(request: Request, code: Optional[str] = None) -> Response:
    """Handle the Discord OAuth2 callback.

    Exchanges the authorization code for an access token, fetches user
    info + guild list, determines the permission role, and issues JWT
    access + refresh tokens.

    Args:
        request: The current FastAPI request.
        code: The authorization code from Discord.

    Returns:
        JSON response with access_token and user info; refresh token set
        as HttpOnly cookie.

    Raises:
        HTTPException: On missing code or Discord API failure.
    """
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    redirect_uri = _get_redirect_uri(request)

    # Exchange code for Discord access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            DISCORD_TOKEN_URL,
            data={
                "client_id": tokens.client_id,
                "client_secret": tokens.client_secret_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if token_resp.status_code != 200:
            log.error(f"Discord token exchange failed: {token_resp.text}")
            raise HTTPException(status_code=502, detail="Discord token exchange failed")

        token_data = token_resp.json()
        discord_access_token = token_data["access_token"]

        # Fetch user info
        user_resp = await client.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {discord_access_token}"},
        )
        if user_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch Discord user info")
        user_data = user_resp.json()

        # Fetch user guilds
        guilds_resp = await client.get(
            f"{DISCORD_API_BASE}/users/@me/guilds",
            headers={"Authorization": f"Bearer {discord_access_token}"},
        )
        guild_ids: list[str] = []
        if guilds_resp.status_code == 200:
            guild_ids = [str(g["id"]) for g in guilds_resp.json()]

    # Determine role
    user_id = str(user_data["id"])
    bot_owner_id = str(getattr(tokens, "bot_owner_id", 0))
    role = "owner" if user_id == bot_owner_id else "user"

    # Check admin permissions for specific guilds
    bot = _get_bot(request)
    admin_guild_ids: list[str] = []
    if bot and role != "owner":
        for gid in guild_ids:
            guild = bot.get_guild(int(gid))
            if guild:
                member = guild.get_member(int(user_id))
                if member and member.guild_permissions.administrator:
                    admin_guild_ids.append(gid)
        if admin_guild_ids:
            role = "admin"

    username = user_data.get("username", "")
    avatar = user_data.get("avatar", "")

    # Issue tokens
    access_token = create_access_token(
        user_id=user_id,
        role=role,
        guild_ids=guild_ids,
        avatar=avatar,
        username=username,
    )
    refresh_token = create_refresh_token(user_id=user_id)

    log.info(f"Dashboard login: user={username} ({user_id}), role={role}")

    # Get frontend URL from config
    dashboard_cfg = getattr(base_config, "dashboard", {})
    cors_origins = dashboard_cfg.get("cors_origins", ["http://localhost:5173"])
    frontend_url = cors_origins[0].rstrip('/')

    redirect_url = f"{frontend_url}/callback?access_token={access_token}"
    log.info(f"OAuth redirect → {frontend_url}/callback?access_token=<JWT:{len(access_token)}chars>")
    response = RedirectResponse(url=redirect_url)
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # Set True in production with HTTPS
        samesite="lax",
        max_age=7 * 86400,
        path="/auth",
    )
    return response


@router.post("/refresh")
async def refresh(request: Request) -> JSONResponse:
    """Refresh the JWT access token using the refresh token cookie.

    Recalculates role and guild_ids from the bot's cached guild state
    so server admins don't lose permissions after token expiry.
    """
    refresh_tok = request.cookies.get("refresh_token")
    if not refresh_tok:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    user_id = await verify_refresh_token_async(refresh_tok)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Re-derive role and guild_ids from bot state (no Discord API call needed)
    bot_owner_id = str(getattr(tokens, "bot_owner_id", 0))
    bot = _get_bot(request)

    if user_id == bot_owner_id:
        role = "owner"
        guild_ids = [str(g.id) for g in bot.guilds] if bot else []
    elif bot:
        guild_ids = []
        admin_guild_ids = []
        for guild in bot.guilds:
            member = guild.get_member(int(user_id))
            if member:
                guild_ids.append(str(guild.id))
                if member.guild_permissions.administrator:
                    admin_guild_ids.append(str(guild.id))
        role = "admin" if admin_guild_ids else "user"
    else:
        role = "user"
        guild_ids = []

    # Preserve avatar and username from old access token if present
    old_auth = request.headers.get("Authorization", "")
    avatar, username = "", ""
    if old_auth.startswith("Bearer "):
        old_payload = verify_access_token(old_auth[7:])
        if old_payload:
            avatar = old_payload.get("avatar", "")
            username = old_payload.get("username", "")

    access_token = create_access_token(
        user_id=user_id,
        role=role,
        guild_ids=guild_ids,
        avatar=avatar,
        username=username,
    )
    return JSONResponse({"access_token": access_token, "token_type": "Bearer"})


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Revoke the refresh token and clear the cookie.

    Returns:
        Success message.
    """
    refresh_tok = request.cookies.get("refresh_token")
    if refresh_tok:
        await revoke_refresh_token_async(refresh_tok)

    response = JSONResponse({"detail": "Logged out"})
    response.delete_cookie(key="refresh_token", path="/auth")
    return response


@router.get("/me")
async def get_current_user(request: Request) -> JSONResponse:
    """Return the currently authenticated user info from the JWT.

    Returns:
        User info and role from the JWT payload.

    Raises:
        HTTPException: On missing/invalid token.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return JSONResponse({
        "id": payload.get("sub"),
        "username": payload.get("username", ""),
        "avatar": payload.get("avatar", ""),
        "role": payload.get("role", "user"),
        "guild_ids": payload.get("guild_ids", []),
    })
