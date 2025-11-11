"""Schema dataclasses for the llm.memory package.

Defines shared memory dataclasses used by various memory providers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from cogs.memory.interfaces.vector_store_interface import MemoryFragment
    from cogs.memory.users.models import UserInfo
else:
    # Fallback types to avoid hard runtime dependency during static analysis or imports.
    MemoryFragment = Any  # type: ignore
    UserInfo = Any  # type: ignore


@dataclass
class ShortTermMemory:
    """Represents short-term memory containing recent messages formatted for the LLM.

    messages example:
        {
            "id": "<discord message id>",
            "author": "<author display name>",
            "content": "<message content>",
            "timestamp": "<ISO8601 timestamp>",
            "reactions": ["👍", "😄"],
            "is_reply_to": "<referenced message id or None>"
        }
    """
    messages: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class EpisodicMemory:
    """Represents episodic memory containing relevant events or facts from a vector store."""
    fragments: List[MemoryFragment] = field(default_factory=list)


@dataclass
class ProceduralMemory:
    """Represents procedural memory containing user-specific background and preferences."""
    user_info: Optional[UserInfo] = None


@dataclass
class SystemContext:
    """The fully assembled context object to be passed to the prompt builder."""
    short_term_memory: ShortTermMemory
    episodic_memory: EpisodicMemory
    procedural_memory: ProceduralMemory
    current_channel_name: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


__all__ = [
    "ShortTermMemory",
    "EpisodicMemory",
    "ProceduralMemory",
    "SystemContext",
]
