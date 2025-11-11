from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

@dataclass
class UserInfo:
    """Information about a single user used by procedural memory."""
    user_background: Optional[str] = None
    procedural_memory: Dict[str, Any] = field(default_factory=dict)
    last_updated: Optional[str] = None

@dataclass
class ProceduralMemory:
    """Holds procedural memory for multiple users keyed by user_id."""
    user_info: Dict[str, UserInfo] = field(default_factory=dict)

@dataclass
class ShortTermMemory:
    """Stores recent messages; each message is a mapping containing at least author_id, author, content, timestamp (numeric UNIX seconds as float)."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
 
@dataclass
class SystemContext:
    """Aggregated context used to build prompts for the LLM."""
    short_term_memory: ShortTermMemory
    procedural_memory: ProceduralMemory
    current_channel_name: str
    timestamp: float = field(default_factory=lambda: datetime.utcnow().timestamp())

__all__ = ["UserInfo", "ProceduralMemory", "ShortTermMemory", "SystemContext"]
