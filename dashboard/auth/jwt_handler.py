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

log = get_logger(server_id="Bot", source=__name__)

# ── Configuration ──────────────────────────────────────────────────────
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 3600        # 1 hour
REFRESH_TOKEN_EXPIRE_SECONDS = 7 * 86400  # 7 days

# Use DASHBOARD_SECRET_KEY from .env; fall back to a random key (dev-only).
_SECRET_KEY: str = getattr(tokens, "secret_key", None) or secrets.token_urlsafe(64)
if not getattr(tokens, "secret_key", None):
    log.warning("DASHBOARD_SECRET_KEY not set in .env — using random key (all tokens invalidated on restart)")

# In-memory refresh token store: {token_str: {"user_id": str, "exp": float}}
_refresh_store: dict[str, dict[str, Any]] = {}


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
    """Create a long-lived opaque refresh token.

    Args:
        user_id: Discord user ID.

    Returns:
        Opaque refresh token string.
    """
    token = secrets.token_urlsafe(48)
    _refresh_store[token] = {
        "user_id": user_id,
        "exp": time.time() + REFRESH_TOKEN_EXPIRE_SECONDS,
    }
    _cleanup_expired_refresh_tokens()
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
    """Verify a refresh token and return the associated user_id.

    Args:
        token: Opaque refresh token string.

    Returns:
        User ID if valid, or ``None``.
    """
    entry = _refresh_store.get(token)
    if entry is None:
        return None
    if time.time() > entry["exp"]:
        _refresh_store.pop(token, None)
        return None
    return entry["user_id"]


def revoke_refresh_token(token: str) -> None:
    """Revoke (delete) a refresh token.

    Args:
        token: Opaque refresh token to revoke.
    """
    _refresh_store.pop(token, None)


def _cleanup_expired_refresh_tokens() -> None:
    """Remove expired entries from the in-memory refresh store."""
    now = time.time()
    expired = [k for k, v in _refresh_store.items() if now > v["exp"]]
    for k in expired:
        del _refresh_store[k]
