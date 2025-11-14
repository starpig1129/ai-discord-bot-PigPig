# cogs/memory/services/message_tracker.py

import discord
from typing import TYPE_CHECKING

from function import func
from addons.settings import MemoryConfig

from cogs.memory.interfaces.storage_interface import StorageInterface

if TYPE_CHECKING:
    from bot import PigPig as Bot

class MessageTracker:
    """
    Tracks new messages in channels for the memory system.
    """

    def __init__(self, bot: 'Bot', storage: 'StorageInterface', settings: MemoryConfig):
        """
        Initializes the MessageTracker.

        Args:
            bot (Bot): The bot instance.
            storage (StorageInterface): The storage backend implementing storage operations.
            settings (MemoryConfig): The settings instance.
        """
        self.bot = bot
        self.storage = storage
        self.settings = settings
        self._pending_message_count = 0

    async def track_message(self, message: discord.Message):
        """
        Tracks a message, adding it to the pending list if it's not from a bot
        and not in an excluded channel. Also updates channel memory state.

        Args:
            message (discord.Message): The message to track.
        """
        if message.author.bot:
            return

        try:
            # Add message to pending list
            await self.storage.add_pending_message(message)
            self._pending_message_count += 1
            
            # Update channel memory state
            channel_id = message.channel.id
            channel_state = await self.storage.get_channel_memory_state(channel_id)
            
            if channel_state is None:
                # Initialize new channel state
                await self.storage.update_channel_memory_state(channel_id, 1, message.id)
            else:
                # Update existing channel state
                new_message_count = channel_state['message_count'] + 1
                await self.storage.update_channel_memory_state(channel_id, new_message_count, channel_state['start_message_id'])
                
        except Exception as e:
            await func.report_error(e, f"Failed to track message {message.id}")

    def get_pending_count(self) -> int:
        """
        Gets the current count of pending messages.

        Returns:
            int: The number of pending messages.
        """
        return self._pending_message_count

    def reset_pending_count(self):
        """
        Resets the pending message count to zero.
        """
        self._pending_message_count = 0