"""Rate limiting middleware using slowapi.

- Auth endpoints: 5 requests / minute per IP
- General API endpoints: 60 requests / minute per user (from JWT sub claim)
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse


def _get_user_or_ip(request: Request) -> str:
    """Extract rate-limit key: authenticated user ID or client IP.

    Args:
        request: The current FastAPI request.

    Returns:
        User ID string if authenticated, otherwise remote IP.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from dashboard.auth.jwt_handler import verify_access_token
            payload = verify_access_token(auth_header[7:])
            if payload and payload.get("sub"):
                return f"user:{payload['sub']}"
        except Exception:
            pass
    return get_remote_address(request)


# Global limiter instance — attached to the FastAPI app in main.py
limiter = Limiter(key_func=_get_user_or_ip)

# Rate limit constants
AUTH_RATE_LIMIT = "5/minute"
API_RATE_LIMIT = "60/minute"


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler for rate limit exceeded errors.

    Args:
        request: The current FastAPI request.
        exc: The RateLimitExceeded exception from slowapi.

    Returns:
        429 JSON response with retry-after information.
    """
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "retry_after": str(exc.detail),
        },
    )
