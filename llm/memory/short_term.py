from typing import List, Any
import re

import discord
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from function import func


class ShortTermMemoryProvider:
    """
    Provides short-term memory as a list of LangChain messages.

    The provider fetches recent message history from the channel and converts
    each Discord message to a LangChain HumanMessage or AIMessage.
    """

    def __init__(self, bot: Any, limit: int = 10):
        """
        Initialize the provider.

        Args:
            limit: maximum number of recent messages to fetch from channel.
        """
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        self.limit = limit
        self.bot = bot

    async def get(self, message: discord.Message) -> List[BaseMessage]:
        """
        Fetch recent messages and return as LangChain BaseMessage list.

        The returned order is oldest -> newest.
        """
        try:
            history = [msg async for msg in message.channel.history(limit=self.limit)][1:]  # Exclude the  bot's message
            history.reverse()

            result: List[BaseMessage] = []
            for msg in history:
                content_parts = []
                if msg.content:
                    cleaned_content = re.sub(rf'<@!?{self.bot.user.id}>', '', msg.content).strip()
                    content_parts.append(f":{cleaned_content}")

                # Include simple textualization for attachments
                if msg.attachments:
                    attach_info = ", ".join(a.filename or "attachment" for a in msg.attachments)
                    content_parts.append(f"[attachments: {attach_info}]")

                # Include embed count if present
                if msg.embeds:
                    content_parts.append(f"[embeds: {len(msg.embeds)}]")

                # Include reactions
                if msg.reactions:
                    reactions_info = ", ".join(str(r.emoji) for r in msg.reactions)
                    content_parts.append(f"[reactions: {reactions_info}]")
                # Include reference info if it's a reply
                if msg.reference:
                    content_parts.append(f"[reply_to: {msg.reference.message_id}]")

                # Prepend author info for clarity
                author_prefix = f"[{msg.author.name} | ID:{msg.id} | {msg.created_at.timestamp()}]"
                combined = " ".join([author_prefix] + content_parts) if content_parts else author_prefix

                if msg.author.bot:
                    result.append(AIMessage(content=combined))
                else:
                    result.append(HumanMessage(content=combined))

            return result
        except Exception as e:
            await func.report_error(e)
            return []
