"""WebSocket log streamer for real-time dashboard log viewing."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from addons.logging import get_logger
from dashboard.auth.jwt_handler import verify_access_token

log = get_logger(server_id="Bot", source=__name__)
router = APIRouter()


class LogStreamer:
    """Manages WebSocket clients and broadcasts log records."""

    BUFFER_SIZE = 200

    def __init__(self) -> None:
        # Use list instead of set — tuples containing dicts are not hashable
        self._clients: list[tuple[WebSocket, dict[str, Any]]] = []
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, filters: dict[str, Any] | None = None) -> None:
        """Accept a new WebSocket client and replay recent logs."""
        await websocket.accept()
        entry = (websocket, filters or {})
        async with self._lock:
            self._clients.append(entry)
        for record in self._buffer:
            if self._matches(record, filters or {}):
                try:
                    await websocket.send_text(json.dumps(record))
                except Exception:
                    break

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket client."""
        async with self._lock:
            self._clients = [(ws, f) for ws, f in self._clients if ws is not websocket]

    async def broadcast(self, record: dict[str, Any]) -> None:
        """Broadcast a log record to all matching connected clients."""
        self._buffer.append(record)
        if len(self._buffer) > self.BUFFER_SIZE:
            self._buffer = self._buffer[-self.BUFFER_SIZE:]
        dead = []
        msg = json.dumps(record)
        for ws, filters in list(self._clients):
            if not self._matches(record, filters):
                continue
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    @staticmethod
    def _matches(record: dict[str, Any], filters: dict[str, Any]) -> bool:
        """Check if a log record matches client filters."""
        if filters.get("guild_id") and record.get("server_id") != filters["guild_id"]:
            return False
        if filters.get("level") and record.get("level", "").upper() != filters["level"].upper():
            return False
        return True


log_streamer = LogStreamer()


@router.websocket("/ws/admin/logs")
async def ws_admin_logs(
    websocket: WebSocket,
    guild_id: str | None = Query(default=None),
    level: str | None = Query(default=None),
    token: str | None = Query(default=None),
) -> None:
    """WebSocket endpoint for streaming all logs (Bot Owner only)."""
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "owner":
        await websocket.close(code=4003, reason="Unauthorized")
        return
    filters = {"guild_id": guild_id, "level": level}
    await log_streamer.connect(websocket, filters)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                update = json.loads(data)
                if "guild_id" in update:
                    filters["guild_id"] = update["guild_id"]
                if "level" in update:
                    filters["level"] = update["level"]
            except (json.JSONDecodeError, TypeError):
                pass
    except WebSocketDisconnect:
        await log_streamer.disconnect(websocket)
    except Exception:
        await log_streamer.disconnect(websocket)


@router.websocket("/ws/guild/{guild_id}/logs")
async def ws_guild_logs(
    websocket: WebSocket,
    guild_id: str,
    level: str | None = Query(default=None),
    token: str | None = Query(default=None),
) -> None:
    """WebSocket endpoint for guild-specific log streaming."""
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    payload = verify_access_token(token)
    if not payload:
        await websocket.close(code=4003, reason="Unauthorized")
        return
    if payload.get("role") != "owner" and guild_id not in payload.get("guild_ids", []):
        await websocket.close(code=4003, reason="No access to this guild")
        return
    filters = {"guild_id": guild_id, "level": level}
    await log_streamer.connect(websocket, filters)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                update = json.loads(data)
                if "level" in update:
                    filters["level"] = update["level"]
            except (json.JSONDecodeError, TypeError):
                pass
    except WebSocketDisconnect:
        await log_streamer.disconnect(websocket)
    except Exception:
        await log_streamer.disconnect(websocket)
