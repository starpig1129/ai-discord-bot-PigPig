"""FastAPI application factory and embedded server launcher.

Creates the dashboard FastAPI app, mounts all routers and middleware,
and provides ``start_dashboard(bot)`` to launch uvicorn inside the
bot's asyncio event loop.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler as _default_rl_handler
from slowapi.errors import RateLimitExceeded

from addons.logging import get_logger
from addons.settings import base_config
from dashboard.auth.discord_oauth import router as auth_router
from dashboard.routers.admin import router as admin_router
from dashboard.routers.guild import router as guild_router
from dashboard.routers.user import router as user_router
from dashboard.routers.stats import router as stats_router
from dashboard.websocket.log_streamer import router as ws_router
from dashboard.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from dashboard.services.stats_collector import StatsCollector

if TYPE_CHECKING:
    from bot import PigPig

log = get_logger(server_id="Bot", source=__name__)


def create_app(bot: "PigPig") -> FastAPI:
    """Create and configure the FastAPI dashboard application.

    Args:
        bot: The PigPig bot instance to attach to app state.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="PigPig Dashboard API",
        version=getattr(base_config, "version", "0.0.0"),
        docs_url="/api/docs",
        redoc_url=None,
    )

    # ── Attach bot + services to app state ────────────────────────────
    app.state.bot = bot
    app.state.stats_collector = bot.stats_collector

    # ── CORS ──────────────────────────────────────────────────────────
    dashboard_cfg = getattr(base_config, "dashboard", {}) or {}
    cors_origins = dashboard_cfg.get("cors_origins", ["http://localhost:5173"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Rate Limiting ─────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # ── Routers ───────────────────────────────────────────────────────
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(guild_router)
    app.include_router(user_router)
    app.include_router(stats_router)
    app.include_router(ws_router)

    # ── Health check ──────────────────────────────────────────────────
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


async def start_dashboard(bot: "PigPig") -> None:
    """Start the dashboard server as an asyncio task in the bot's loop.

    Reads host/port from ``base_config.dashboard`` and launches
    uvicorn programmatically without blocking the event loop.

    Args:
        bot: The PigPig bot instance.
    """
    dashboard_cfg = getattr(base_config, "dashboard", {}) or {}
    if not dashboard_cfg.get("enabled", True):
        log.info("Dashboard is disabled in config — skipping startup.")
        return

    host = dashboard_cfg.get("host", "0.0.0.0")
    port = dashboard_cfg.get("port", 8005)

    app = create_app(bot)

    # Initialize stats database
    await app.state.stats_collector.initialize()

    # Initialize persistent refresh token store
    from dashboard.auth import token_store as _token_store
    try:
        await _token_store.initialize()
        log.info("Refresh token store initialized")
    except Exception as exc:
        log.error(f"Refresh token store initialization failed: {exc}")

    # Store reference on bot for graceful shutdown
    bot._dashboard_app = app

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    bot._dashboard_server = server

    log.info(f"Dashboard starting on http://{host}:{port}")
    asyncio.create_task(server.serve())


async def stop_dashboard(bot: "PigPig") -> None:
    """Gracefully stop the dashboard server.

    Args:
        bot: The PigPig bot instance.
    """
    server = getattr(bot, "_dashboard_server", None)
    if server:
        server.should_exit = True
        log.info("Dashboard server stopped.")
