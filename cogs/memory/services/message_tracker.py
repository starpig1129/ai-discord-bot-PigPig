# cogs/memory/services/message_tracker.py

import asyncio
import discord
import logging
from typing import TYPE_CHECKING

from function import func
from addons.settings import MemoryConfig

from cogs.memory.interfaces.storage_interface import StorageInterface
from cogs.memory.services.event_summarization_service import EventSummarizationService, EventSummary
from cogs.memory.services.vectorization_service import VectorizationService

if TYPE_CHECKING:
    from bot import PigPig as Bot

logger = logging.getLogger(__name__)

def discord_id_to_unix_timestamp(message_id: int) -> float:
    """
    Convert Discord message ID to Unix timestamp in milliseconds.
    
    Args:
        message_id (int): The Discord message ID
        
    Returns:
        float: The Unix timestamp in milliseconds when the message was created
    """
    DISCORD_EPOCH = 1420070400000  # Discord epoch in milliseconds
    return ((message_id >> 22) + DISCORD_EPOCH) / 1000

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
                
                # Check if message threshold is reached
                if new_message_count >= self.settings.message_threshold:
                    # Log threshold reached and trigger async task
                    logger.info(f"Message threshold reached for channel {channel_id} (count: {new_message_count}), triggering memory processing")
                    # Ensure channel is a TextChannel before passing to _process_channel_memory
                    if isinstance(message.channel, discord.TextChannel):
                        asyncio.create_task(self._process_channel_memory(message.channel))
                    else:
                        logger.warning(f"Skipping memory processing for non-text channel {channel_id}")
                
        except Exception as e:
            await func.report_error(e, f"Failed to track message {message.id}")

    async def _process_channel_memory(self, channel: discord.TextChannel):
        """
        Processes memory for a channel when threshold is reached.
        
        Args:
            channel (discord.TextChannel): The channel to process memory for.
        """
        try:
            logger.info(f"Processing memory for channel {channel.id}")
            
            # Get channel state
            state = await self.storage.get_channel_memory_state(channel.id)
            if not state:
                logger.error(f"No memory state found for channel {channel.id}")
                return
            
            # Get start message
            start_message = None
            try:
                start_message = await channel.fetch_message(state['start_message_id'])
            except discord.NotFound:
                logger.warning(f"Start message {state['start_message_id']} not found in channel {channel.id}, calculating timestamp from ID")
            except discord.Forbidden:
                logger.error(f"Permission denied to fetch start message {state['start_message_id']} in channel {channel.id}")
                return
                
            # Get message history
            all_messages = []
            
            if start_message:
                # Use the actual message object
                all_messages.append(start_message)
                start_timestamp = start_message.created_at
            else:
                # Calculate timestamp from message ID when message is not found
                start_timestamp = discord.utils.snowflake_time(state['start_message_id'])
                logger.info(f"Calculated timestamp from message ID: {start_timestamp}")
            
            # Get messages after the calculated/found timestamp
            messages = []
            async for message in channel.history(after=start_timestamp, limit=None):
                messages.append(message)
            
            all_messages.extend(messages)
            
            logger.info(f"Retrieved {len(all_messages)} messages for processing in channel {channel.id}")
            
            # Initialize EventSummarizationService
            summarization_service = EventSummarizationService(self.bot, self.settings)
            
            # Call event summarization
            messages_to_process = all_messages
            event_summaries = await summarization_service.summarize_events(messages_to_process)
            
            # Check if event summaries is empty
            if not event_summaries:
                logger.info(f"No events summarized from {len(messages_to_process)} messages in channel {channel.id}")
                return
            
            # Log successful retrieval of event summaries
            logger.info(f"Successfully retrieved {len(event_summaries)} event summaries from channel {channel.id}")
            
            # Initialize VectorizationService
            vector_manager = getattr(self.bot, "vector_manager", None)
            vectorization_service = VectorizationService(
                bot=self.bot,
                storage=self.storage,
                vector_manager=vector_manager,
                settings=self.settings
            )
            
            # Process event summaries through VectorizationService
            await vectorization_service.process_event_summaries(event_summaries)
            
            # Log successful submission of event summaries to VectorizationService
            logger.info(f"Successfully submitted {len(event_summaries)} event summaries from channel {channel.id} to vectorization service")
            
            # Update channel memory state for next processing cycle
            await self.storage.update_channel_memory_state(
                channel_id=channel.id,
                message_count=0,
                start_message_id=messages_to_process[-1].id
            )
            
            # Log successful update of channel memory state
            logger.info(f"Successfully updated memory state for channel {channel.id}, new start_message_id: {messages_to_process[-1].id}")
            
        except Exception as e:
            await func.report_error(e, f"Failed to process memory for channel {channel.id}")

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