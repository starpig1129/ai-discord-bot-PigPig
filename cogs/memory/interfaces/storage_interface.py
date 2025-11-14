from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import discord

if TYPE_CHECKING:
    from ..users.manager import UserInfo


class ProceduralStorageInterface(ABC):
    """Interface for procedural (user) storage operations."""

    @abstractmethod
    async def get_user_info(self, discord_id: str) -> Optional["UserInfo"]:
        raise NotImplementedError

    @abstractmethod
    async def update_user_data(
        self,
        discord_id: str,
        discord_name: str,
        procedural_memory: Optional[str] = None,
        user_background: Optional[str] = None,
        display_names: Optional[List[str]] = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def update_user_activity(self, discord_id: str, discord_name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_config(self, key: str) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    async def set_config(self, key: str, value: str) -> None:
        raise NotImplementedError


class EpisodicStorageInterface(ABC):
    """Interface for episodic (channel memory state) storage operations."""

    @abstractmethod
    async def initialize_channel_memory_state(self) -> None:
        """Initialize the channel_memory_state table in the database."""
        raise NotImplementedError

    @abstractmethod
    async def get_channel_memory_state(self, channel_id: int) -> Optional[Dict[str, int]]:
        """Get the memory state for a specific channel.
        
        Args:
            channel_id (int): The channel ID to get state for.
            
        Returns:
            Optional[Dict[str, int]]: Dictionary with 'message_count' and 'start_message_id', or None if not found.
        """
        raise NotImplementedError

    @abstractmethod
    async def update_channel_memory_state(self, channel_id: int, message_count: int, start_message_id: int) -> None:
        """Update the memory state for a specific channel.
        
        Args:
            channel_id (int): The channel ID to update state for.
            message_count (int): The new message count.
            start_message_id (int): The start message ID.
        """
        raise NotImplementedError


class StorageInterface(ProceduralStorageInterface, EpisodicStorageInterface):
    """Combined interface kept for backward compatibility."""
    pass