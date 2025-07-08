import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field


@dataclass
class Event:
    """Represents a specific event that occurred at a location."""
    title: str
    summary: str
    full_content: str
    timestamp: str


@dataclass
class Location:
    """Represents a specific location within the story world."""
    name: str
    events: List[Event] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StoryWorld:
    """Represents the lore and rules of a story world, acting as a container for locations."""
    guild_id: int
    world_name: str
    locations: List[Location] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StoryCharacter:
    """Represents a character, either player-controlled (PC) or non-player (NPC)."""
    name: str
    description: str
    guild_id: int  # The guild this character belongs to, for data isolation
    creator_id: int
    is_pc: bool = False
    user_id: Optional[int] = None
    is_public: bool = True
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
    current_date: Optional[str]
    current_time: Optional[str]
    current_location: str
    is_active: bool = True
    active_character_ids: List[str] = field(default_factory=list)
    current_state: Dict[str, Any] = field(default_factory=dict)
    event_log: List[str] = field(default_factory=list)
    message_counter: int = 0
    summaries: List[str] = field(default_factory=list)
    outlines: List[str] = field(default_factory=list)
    narration_enabled: bool = True

@dataclass
class PlayerRelationship:
    """Represents the relationship between a player (user) and an NPC."""
    story_id: int  # Corresponds to channel_id from StoryInstance
    character_id: str
    user_id: int
    description: str
    relationship_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# --- Pydantic Schemas for Structured Output ---

class DialogueContext(BaseModel):
    speaker_name: str = Field(..., description="The name of the character who is speaking.")
    motivation: str = Field(..., description="The character's goal or reason for this dialogue.")
    emotional_state: str = Field(..., description="The character's current emotional state (e.g., angry, happy, curious).")

class StateUpdate(BaseModel):
    location: str = Field(..., description="The new location name. This is mandatory.")
    date: str = Field(..., description="The new date. This is mandatory.")
    time: str = Field(..., description="The new time. This is mandatory.")

class RelationshipUpdate(BaseModel):
    character_name: str = Field(..., description="The name of the NPC whose relationship is changing.")
    user_name: str = Field(..., description="The display name of the player involved.")
    description: str = Field(..., description="The new, updated description of the relationship.")

class GMActionPlan(BaseModel):
    """
    The Game Master's action plan, defining the next step in the story.
    This structure is used for the AI's structured output.
    """
    action_type: str = Field(
        ...,
        description="The type of action to be taken. MUST be one of: 'NARRATE' or 'DIALOGUE'."
    )
    
    event_title: str = Field(..., description="A short, concise title for this event, suitable for memory logs.")
    event_summary: str = Field(..., description="A one-sentence summary of this event for long-term memory.")
    state_update: Optional[StateUpdate] = Field(default=None, description="The complete, updated world state. This is always required.")
    narration_content: Optional[str] = Field(default=None, description="The narration text, required if action_type is NARRATE.")
    dialogue_context: Optional[List[DialogueContext]] = Field(
        default=None,
        description="A list of dialogue contexts for Character Agents, allowing multiple characters to speak. Required if action_type is DIALOGUE."
    )
    relationships_update: Optional[List[RelationshipUpdate]] = Field(
        default=None,
        description="Include this array ONLY if player-NPC relationships change."
    )


class CharacterAction(BaseModel):
    """
    Represents a character's action, combining dialogue, physical action, and internal thought.
    This structure is used for the AI's structured output.
    """
    action: Optional[str] = Field(default=None, description="The character's action,body language or facial expressions.")
    dialogue: str = Field(description="Words spoken by the character.")
    thought: Optional[str] = Field(default=None, description="The inner thoughts or feelings of the character, visible to the player.")
    location: str = Field(description="The specific location where the character is performing this action.")
    date: str = Field(description="The date when the character is performing this action.")
    time: str = Field(description="The time when the character is performing this action.")