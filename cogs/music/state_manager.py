import discord
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class PlayerState:
    current_song: Optional[Dict[str, Any]] = None
    current_message: Optional[discord.Message] = None
    current_view: Optional[Any] = None
    
class StateManager:
    def __init__(self):
        self.states: Dict[int, PlayerState] = {}
        
    def get_state(self, guild_id: int) -> PlayerState:
        """Get or create state for a guild"""
        if guild_id not in self.states:
            self.states[guild_id] = PlayerState()
        return self.states[guild_id]
        
    def update_state(self, guild_id: int, **kwargs):
        """Update state attributes for a guild"""
        state = self.get_state(guild_id)
        for key, value in kwargs.items():
            setattr(state, key, value)
            
    def clear_state(self, guild_id: int):
        """Clear state for a guild"""
        if guild_id in self.states:
            del self.states[guild_id]
