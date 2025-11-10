from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import discord

if TYPE_CHECKING:
    from ..users.manager import UserInfo


class StorageInterface(ABC):
    """Abstract base interface for high-level storage operations."""

    @abstractmethod
    async def get_user_info(self, discord_id: str) -> Optional["UserInfo"]:
        """Retrieve user information by user_id."""
        raise NotImplementedError

    @abstractmethod
    async def update_user_data(self, discord_id: str, procedural_memory: str, discord_name: str) -> bool:
        """Update user's data and display name."""
        raise NotImplementedError

    @abstractmethod
    async def update_user_activity(self, discord_id: str, discord_name: str) -> bool:
        """Update user's last activity and optionally display name."""
        raise NotImplementedError

    @abstractmethod
    async def add_pending_message(self, message: discord.Message) -> None:
        """Add a message to the pending queue for processing."""
        raise NotImplementedError

    @abstractmethod
    async def get_pending_messages(self, limit: int) -> List[Dict[str, Any]]:
        """Retrieve a batch of pending messages."""
        raise NotImplementedError

    @abstractmethod
    async def mark_pending_messages_processed(self, pending_ids: List[int]) -> None:
        """Mark pending messages (by pending record ids) as processed."""
        raise NotImplementedError

    @abstractmethod
    async def store_messages_batch(self, messages: List[discord.Message]) -> None:
        """Store a batch of full message objects for later vectorization."""
        raise NotImplementedError

    @abstractmethod
    async def get_unprocessed_messages(self, limit: int) -> List[Dict[str, Any]]:
        """Retrieve a batch of messages that have not yet been vectorized."""
        raise NotImplementedError

    @abstractmethod
    async def mark_messages_vectorized(self, message_ids: List[int]) -> None:
        """Mark a batch of messages as vectorized."""
        raise NotImplementedError

    @abstractmethod
    async def get_config(self, key: str) -> Optional[str]:
        """Retrieve a configuration value by key."""
        raise NotImplementedError

    @abstractmethod
    async def set_config(self, key: str, value: str) -> None:
        """Set a configuration value by key."""
        raise NotImplementedError