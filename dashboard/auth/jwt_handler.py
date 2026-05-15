"""JWT token creation and verification for dashboard authentication.

Uses python-jose for JWT operations with HS256 algorithm.
Access tokens (1hr) carried in Authorization header;
Refresh tokens (7d) stored in HttpOnly cookies.
"""

from __future__ import annotations

import time
import secrets
from typing import Any, Optional

from jose import JWTError, jwt

from addons.logging import get_logger
from addons.tokens import tokens
from dashboard.auth import token_store

log = get_logger(server_id="Bot", source=__name__)

# ── Configuration ──────────────────────────────────────────────────────
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 3600        # 1 hour
REFRESH_TOKEN_EXPIRE_SECONDS = 7 * 86400  # 7 days

# Use DASHBOARD_SECRET_KEY from .env; fall back to a random key (dev-only).
_SECRET_KEY: str = getattr(tokens, "secret_key", None) or secrets.token_urlsafe(64)
if not getattr(tokens, "secret_key", None):
    log.warning("DASHBOARD_SECRET_KEY not set in .env — using random key (all tokens invalidated on restart)")

# NOTE: In-memory refresh token store removed; persistence is handled by token_store (SQLite).


def create_access_token(
    user_id: str,
    role: str,
    guild_ids: list[str],
    avatar: str = "",
    username: str = "",
) -> str:
    """Create a short-lived JWT access token.

    Args:
        user_id: Discord user ID.
        role: Permission role ("owner", "admin", "user").
        guild_ids: List of guild IDs the user belongs to.
        avatar: Discord avatar hash.
        username: Discord username.

    Returns:
        Encoded JWT string.
    """
    now = time.time()
    payload = {
        "sub": user_id,
        "role": role,
        "guild_ids": guild_ids,
        "avatar": avatar,
        "username": username,
        "iat": now,
        "exp": now + ACCESS_TOKEN_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived opaque refresh token and schedule persistence.

    Args:
        user_id: Discord user ID.

    Returns:
        Opaque refresh token string.
    """
    token = secrets.token_urlsafe(48)
    exp = time.time() + REFRESH_TOKEN_EXPIRE_SECONDS
    import asyncio

    def _log_store_error(task: asyncio.Task) -> None:
        """Log any exceptions from the token store task."""
        if task.exception():
            log.error(f"Refresh token persist failed for user {user_id}: {task.exception()}")

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(token_store.store(token, user_id, exp))
        task.add_done_callback(_log_store_error)
    except RuntimeError:
        log.debug("No running event loop; token_store.store() not scheduled")
    return token


def verify_access_token(token: str) -> Optional[dict[str, Any]]:
    """Verify and decode a JWT access token.

    Args:
        token: Encoded JWT string.

    Returns:
        Decoded payload dict, or ``None`` if invalid/expired.
    """
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        log.debug(f"JWT verification failed: {exc}")
        return None


def verify_refresh_token(token: str) -> Optional[str]:
    """Sync shim — prefer verify_refresh_token_async in async contexts.

    Args:
        token: Opaque refresh token string.

    Returns:
        User ID if valid, or ``None``.
    """
    import asyncio
    try:
        return asyncio.get_event_loop().run_until_complete(token_store.lookup(token))
    except Exception:
        return None


def revoke_refresh_token(token: str) -> None:
    """Sync shim — prefer revoke_refresh_token_async in async contexts.

    Args:
        token: Opaque refresh token to revoke.
    """
    import asyncio
    try:
        asyncio.get_event_loop().run_until_complete(token_store.revoke(token))
    except Exception:
        pass


async def verify_refresh_token_async(token: str) -> str | None:
    """Async verify using persistent store.

    Args:
        token: Opaque refresh token string.

    Returns:
        User ID if valid, or ``None``.
    """
    return await token_store.lookup(token)


async def revoke_refresh_token_async(token: str) -> None:
    """Async revoke using persistent store.

    Args:
        token: Opaque refresh token to revoke.
    """
    await token_store.revoke(token)
