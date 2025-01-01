import asyncio
import random
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class PlayMode(Enum):
    NO_LOOP = "no_loop"
    LOOP_QUEUE = "loop_queue" 
    LOOP_SINGLE = "loop_single"

@dataclass
class QueueState:
    queue: asyncio.Queue
    play_mode: PlayMode = PlayMode.NO_LOOP
    shuffle_enabled: bool = False
    playlist: List[Dict[str, Any]] = None
    
class QueueManager:
    def __init__(self):
        self.guild_queues: Dict[int, QueueState] = {}
        
    def get_queue_state(self, guild_id: int) -> QueueState:
        """Get or create queue state for a guild"""
        if guild_id not in self.guild_queues:
            self.guild_queues[guild_id] = QueueState(asyncio.Queue())
        return self.guild_queues[guild_id]
        
    def get_queue(self, guild_id: int) -> asyncio.Queue:
        """Get the queue for a guild"""
        return self.get_queue_state(guild_id).queue
        
    def set_play_mode(self, guild_id: int, mode: str):
        """Set the play mode for a guild"""
        state = self.get_queue_state(guild_id)
        state.play_mode = PlayMode(mode)
        
    def get_play_mode(self, guild_id: int) -> PlayMode:
        """Get the play mode for a guild"""
        return self.get_queue_state(guild_id).play_mode
        
    def toggle_shuffle(self, guild_id: int) -> bool:
        """Toggle shuffle mode for a guild"""
        state = self.get_queue_state(guild_id)
        state.shuffle_enabled = not state.shuffle_enabled
        return state.shuffle_enabled
        
    def is_shuffle_enabled(self, guild_id: int) -> bool:
        """Check if shuffle is enabled for a guild"""
        return self.get_queue_state(guild_id).shuffle_enabled
        
    async def add_to_queue(self, guild_id: int, item: Dict[str, Any]):
        """Add an item to the queue"""
        queue = self.get_queue(guild_id)
        await queue.put(item)
        
    async def get_next_item(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get the next item from the queue"""
        queue = self.get_queue(guild_id)
        if queue.empty():
            return None
        return await queue.get()
        
    def set_playlist(self, guild_id: int, playlist: List[Dict[str, Any]]):
        """Set the playlist for a guild"""
        state = self.get_queue_state(guild_id)
        state.playlist = playlist
        
    def has_playlist_songs(self, guild_id: int) -> bool:
        """Check if there are songs in the playlist"""
        state = self.get_queue_state(guild_id)
        return bool(state.playlist)
        
    async def get_next_playlist_songs(self, guild_id: int, count: int) -> List[Dict[str, Any]]:
        """Get the next songs from the playlist"""
        state = self.get_queue_state(guild_id)
        if not state.playlist:
            return []
            
        songs = state.playlist[:count]
        state.playlist = state.playlist[count:]
        return songs
        
    async def copy_queue(self, guild_id: int, shuffle: bool = False) -> Tuple[List[Dict[str, Any]], asyncio.Queue]:
        """Copy the queue and optionally shuffle it"""
        queue = self.get_queue(guild_id)
        queue_copy = []
        new_queue = asyncio.Queue()
        
        # Copy items from the queue
        while not queue.empty():
            item = await queue.get()
            queue_copy.append(item)
            await new_queue.put(item)
            
        if shuffle:
            random.shuffle(queue_copy)
            # Clear and refill the new queue with shuffled items
            new_queue = asyncio.Queue()
            for item in queue_copy:
                await new_queue.put(item)
                
        return queue_copy, new_queue
        
    def clear_guild_data(self, guild_id: int):
        """Clear all queue data for a guild"""
        if guild_id in self.guild_queues:
            del self.guild_queues[guild_id]
