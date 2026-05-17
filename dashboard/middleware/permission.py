"""Permission verification middleware for the dashboard.

Provides FastAPI dependencies for role-based access control:
- ``get_current_user``  — extracts and validates JWT from Authorization header
- ``require_owner``     — restricts to Bot Owner only
- ``require_admin``     — restricts to Server Admin or Bot Owner
- ``require_guild_access`` — validates access to a specific guild
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, HTTPException, Depends

from addons.logging import get_logger
from dashboard.auth.jwt_handler import verify_access_token

log = get_logger(server_id="Bot", source=__name__)


async def get_current_user(request: Request) -> dict[str, Any]:
    """Extract and verify the JWT from the Authorization header.

    Args:
        request: The current FastAPI request.

    Returns:
        Decoded JWT payload dict with keys: sub, role, guild_ids, etc.

    Raises:
        HTTPException: 401 if token is missing, invalid, or expired.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload


async def require_owner(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Dependency that requires the Bot Owner role.

    Args:
        user: Decoded JWT payload (injected by ``get_current_user``).

    Returns:
        The same user payload if authorized.

    Raises:
        HTTPException: 403 if the user is not the Bot Owner.
    """
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Bot Owner access required")
    return user


async def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Dependency that requires at least Server Admin role.

    Args:
        user: Decoded JWT payload.

    Returns:
        The user payload if authorized.

    Raises:
        HTTPException: 403 if role is not owner or admin.
    """
    if user.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_guild_access(guild_id: str, user: dict[str, Any]) -> None:
    """Verify that the user has access to the specified guild.

    Bot Owners have access to all guilds.  Server Admins are restricted
    to guilds listed in their JWT ``guild_ids`` claim.

    Args:
        guild_id: The guild ID being accessed.
        user: Decoded JWT payload.

    Raises:
        HTTPException: 403 if the user lacks access to the guild.
    """
    if user.get("role") == "owner":
        return  # Owner has unrestricted access

    user_guilds = user.get("guild_ids", [])
    if guild_id not in user_guilds:
        raise HTTPException(
            status_code=403,
            detail=f"No access to guild {guild_id}",
        )
