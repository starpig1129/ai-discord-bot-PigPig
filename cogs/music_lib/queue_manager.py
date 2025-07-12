import asyncio
from typing import List, Dict, Any, Tuple, Optional
from enum import Enum

from . import queue

class PlayMode(Enum):
    NO_LOOP = "no_loop"
    LOOP_QUEUE = "loop_queue"
    LOOP_SINGLE = "loop_single"

class QueueManager:
    def get_queue(self, guild_id: int) -> asyncio.Queue:
        """Get the queue for a guild"""
        q, _ = queue.get_guild_queue_and_folder(guild_id)
        return q

    def set_play_mode(self, guild_id: int, mode: PlayMode):
        """Set the play mode for a guild"""
        queue.set_play_mode(guild_id, mode.value)

    def get_play_mode(self, guild_id: int) -> PlayMode:
        """Get the play mode for a guild"""
        mode_str = queue.get_play_mode(guild_id)
        return PlayMode(mode_str)

    def toggle_shuffle(self, guild_id: int) -> bool:
        """Toggle shuffle mode for a guild"""
        return queue.toggle_shuffle(guild_id)

    def is_shuffle_enabled(self, guild_id: int) -> bool:
        """Check if shuffle is enabled for a guild"""
        return queue.is_shuffle_enabled(guild_id)

    async def add_to_queue(self, guild_id: int, item: Dict[str, Any]):
        """Add an item to the queue"""
        q = self.get_queue(guild_id)
        await q.put(item)

    async def get_next_item(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get the next item from the queue"""
        q = self.get_queue(guild_id)
        if q.empty():
            return None
        return await q.get()

    def set_playlist(self, guild_id: int, playlist: List[Dict[str, Any]]):
        """Set the playlist for a guild"""
        queue.set_guild_playlist(guild_id, playlist)

    def has_playlist_songs(self, guild_id: int) -> bool:
        """Check if there are songs in the playlist"""
        return queue.has_playlist_songs(guild_id)

    async def get_next_playlist_songs(self, guild_id: int, count: int) -> List[Dict[str, Any]]:
        """Get the next songs from the playlist"""
        return await queue.get_next_playlist_songs(guild_id, count)

    async def copy_queue(self, guild_id: int, shuffle: bool = False) -> Tuple[List[Dict[str, Any]], asyncio.Queue]:
        """Copy the queue and optionally shuffle it"""
        return await queue.copy_queue(guild_id, shuffle)

    def clear_guild_data(self, guild_id: int):
        """Clear all queue data for a guild"""
        queue.clear_guild_queue(guild_id)

    def set_queue(self, guild_id: int, q: asyncio.Queue):
        """Set the queue for a guild"""
        queue.set_guild_queue(guild_id, q)
