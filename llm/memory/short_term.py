from typing import List, Dict, Any
import discord

from llm.memory.schema import ShortTermMemory
from function import func


class ShortTermMemoryProvider:
    """
    Provides short-term memory by fetching recent message history from a channel.
    """

    def __init__(self, limit: int = 10):
        """
        Initializes the provider with a message history limit.

        Args:
            limit (int): The maximum number of recent messages to fetch.
        """
        self.limit = limit

    async def get(self, message: discord.Message) -> ShortTermMemory:
        """
        Fetches recent messages from the message's channel and formats them.

        Args:
            message (discord.Message): The current message to use as a reference point.

        Returns:
            ShortTermMemory: An object containing the list of formatted recent messages.
        """
        try:
            history = [msg async for msg in message.channel.history(limit=self.limit)]
            # Reverse the history to have the oldest message first
            history.reverse()

            formatted_messages: List[Dict[str, Any]] = []
            for msg in history:
                formatted_messages.append({
                    "id": msg.id,
                    "author": msg.author.name,
                    "content": msg.content,
                    "reactions": [str(reaction.emoji) for reaction in msg.reactions],
                    "is_reply_to": msg.reference.message_id if msg.reference else None,
                    "timestamp": msg.created_at.isoformat()
                })

            return ShortTermMemory(messages=formatted_messages)
        except Exception as e:
            # Use centralized error reporting as required by project rules.
            await func.report_error(e)
            return ShortTermMemory(messages=[])