from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, Optional
import discord
from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="llm.utils.safe_typing")

class SafeTyping:
    """Typing indicator that handles per-channel deduplication and rate-limiting.
    
    This class ensures that only one typing heart-beat loop is running per channel,
    even if multiple tasks are processing messages for the same channel.
    It also enforces a minimum interval between trigger_typing() calls and
    handles 429 rate limits gracefully.
    """

    _sessions: Dict[int, int] = {}  # channel_id -> active session count
    _tasks: Dict[int, asyncio.Task] = {}  # channel_id -> background loop task
    _last_trigger: Dict[int, float] = {}  # channel_id -> last call timestamp
    _lock = asyncio.Lock()

    _INTERVAL = 9.0  # seconds between keep-alive sends (Discord drops typing after ~10 s)
    _BACKOFF = 30.0  # seconds to wait after a 429 before trying again
    _MIN_CALL_DELAY = 5.0  # minimum seconds between API calls for the same channel

    def __init__(self, channel: Any) -> None:
        self._channel = channel
        self._channel_id = getattr(channel, "id", 0)

    async def _loop(self, channel_id: int) -> None:
        """Background loop to keep the typing indicator alive."""
        try:
            while True:
                await asyncio.sleep(self._INTERVAL)
                
                async with self._lock:
                    # If no more sessions are active for this channel, exit the loop
                    if self._sessions.get(channel_id, 0) <= 0:
                        break
                    
                    # Respect minimum delay between calls
                    now = time.time()
                    if now - self._last_trigger.get(channel_id, 0) < self._MIN_CALL_DELAY:
                        continue

                    try:
                        await self._channel.trigger_typing()
                        self._last_trigger[channel_id] = time.time()
                    except discord.HTTPException as exc:
                        if exc.status == 429:
                            logger.warning(f"Typing 429 for channel {channel_id}, backing off for {self._BACKOFF}s")
                            await asyncio.sleep(self._BACKOFF)
                        else:
                            logger.error(f"HTTP error during typing for channel {channel_id}: {exc}")
                            break
                    except Exception as e:
                        logger.error(f"Unexpected error during typing for channel {channel_id}: {e}")
                        break
        finally:
            async with self._lock:
                if self._tasks.get(channel_id) == asyncio.current_task():
                    self._tasks.pop(channel_id, None)
                    self._sessions.pop(channel_id, None)

    async def __aenter__(self) -> "SafeTyping":
        if not self._channel_id:
            return self

        async with self._lock:
            # Increment session count
            self._sessions[self._channel_id] = self._sessions.get(self._channel_id, 0) + 1
            
            # Initial trigger if needed
            now = time.time()
            if now - self._last_trigger.get(self._channel_id, 0) >= self._MIN_CALL_DELAY:
                try:
                    await self._channel.trigger_typing()
                    self._last_trigger[self._channel_id] = time.time()
                except Exception as e:
                    logger.debug(f"Initial typing trigger failed for channel {self._channel_id}: {e}")

            # Start background loop if not already running
            if self._channel_id not in self._tasks:
                self._tasks[self._channel_id] = asyncio.create_task(
                    self._loop(self._channel_id),
                    name=f"SafeTyping-{self._channel_id}"
                )
        
        return self

    async def __aexit__(self, *_: Any) -> None:
        if not self._channel_id:
            return

        async with self._lock:
            self._sessions[self._channel_id] = max(0, self._sessions.get(self._channel_id, 1) - 1)
            # We don't cancel the task here; the loop will check the session count and exit naturally
            # This allows short-lived overlapping sessions to keep the loop alive efficiently.
