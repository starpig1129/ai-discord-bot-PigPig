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
    """Interface for episodic (message) storage operations."""

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
    async def archive_messages(self, message_ids: List[int]) -> None:
        """Move vectorized messages from the primary table to the archive table."""
        raise NotImplementedError

    @abstractmethod
    async def delete_messages(self, message_ids: List[int]) -> None:
        """Delete messages from the primary messages table."""
        raise NotImplementedError


class StorageInterface(ProceduralStorageInterface, EpisodicStorageInterface):
    """Combined interface kept for backward compatibility."""
    pass