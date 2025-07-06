import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class StoryWorld:
    """Represents the lore and rules of a story world."""
    guild_id: int
    world_name: str
    background: str
    rules: List[str] = field(default_factory=list)
    elements: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StoryCharacter:
    """Represents a character, either player-controlled (PC) or non-player (NPC)."""
    world_name: str
    name: str
    description: str
    is_pc: bool = False
    user_id: Optional[int] = None
    webhook_url: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    inventory: List[str] = field(default_factory=list)
    status: str = "Normal"
    character_id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass
class StoryInstance:
    """Represents an active story session in a specific channel."""
    channel_id: int
    guild_id: int
    world_name: str
    current_date: str
    current_time: str
    current_location: str
    is_active: bool = True
    active_characters: List[str] = field(default_factory=list) # List of character_id
    current_state: Dict[str, Any] = field(default_factory=dict)
    event_log: List[str] = field(default_factory=list)

@dataclass
class PlayerRelationship:
    """Represents the relationship between a player (user) and an NPC."""
    story_id: int  # Corresponds to channel_id from StoryInstance
    character_id: str
    user_id: int
    description: str
    relationship_id: str = field(default_factory=lambda: str(uuid.uuid4()))