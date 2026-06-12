import asyncio
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
            from llm.utils.attachment_processor import process_attachment
            from llm.utils.embed_processor import process_embed
            from addons.settings import attachment_config as _att_cfg

            history = [
                msg async for msg in message.channel.history(limit=self.limit)
            ]
            history.reverse()

            # Collect all attachment processing tasks upfront to process concurrently
            attachment_tasks = []
            attachment_task_indices = []  # Maps task index back to (msg_index, attachment)

            for msg_idx, msg in enumerate(history):
                if msg.attachments and _att_cfg.enabled:
                    for attachment in msg.attachments:
                        attachment_tasks.append(process_attachment(attachment))
                        attachment_task_indices.append(msg_idx)

            # Execute all attachment tasks concurrently
            processed_attachments_by_msg = {i: [] for i in range(len(history))}
            if attachment_tasks:
                results = await asyncio.gather(*attachment_tasks, return_exceptions=True)
                for i, result_parts in enumerate(results):
                    msg_idx = attachment_task_indices[i]
                    if isinstance(result_parts, Exception):
                        # On failure, we could log it. process_attachment is meant to handle
                        # its own exceptions and return a fallback text part, but just in case:
                        from addons.logging import get_logger
                        log = get_logger(source=__name__, server_id="system")
                        log.warning(f"Attachment processing raised exception: {result_parts}")
                        processed_attachments_by_msg[msg_idx].extend(
                            [{"type": "text", "text": "[Attachment processing failed]"}]
                        )
                    else:
                        processed_attachments_by_msg[msg_idx].extend(result_parts)

            result: List[BaseMessage] = []
            for msg_idx, msg in enumerate(history):
                content_parts = []
                content_suffix = []

                content_prefix = f"{msg.author.name} | UserID:{msg.author.id} | MessageID:{msg.id}"

                # Include reactions
                if msg.reactions:
                    reactions_info = ", ".join(str(r.emoji) for r in msg.reactions)
                    content_suffix.append(f"reactions: {reactions_info}")
                # Include reference info if it's a reply
                if msg.reference:
                    ref_text = f"reply_to: {msg.reference.message_id}"
                    ref_msg = None
                    if hasattr(msg.reference, "resolved") and isinstance(msg.reference.resolved, discord.Message):
                        ref_msg = msg.reference.resolved
                    elif hasattr(msg.reference, "cached_message") and msg.reference.cached_message:
                        ref_msg = msg.reference.cached_message

                    if ref_msg:
                        ref_author = ref_msg.author.name
                        # Create a brief summary of the referenced content
                        ref_content = ref_msg.content.replace('\n', ' ')[:50]
                        if len(ref_msg.content) > 50:
                            ref_content += "..."
                        if not ref_content and ref_msg.attachments:
                            ref_content = "[Image/Attachment]"
                        ref_text = f"Replying to @{ref_author}: '{ref_content}' (MessageID:{msg.reference.message_id})"
                        
                    content_suffix.append(ref_text)

                # Provide both Unix timestamp and human-readable time
                ts = msg.created_at.timestamp()
                human_time = msg.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
                content_suffix.append(f"timestamp: {ts} ({human_time})")

                if msg.content:
                    cleaned_content = re.sub(rf'<@!?{self.bot.user.id}>', '', msg.content).strip()
                    content_parts.append({"type": "text", "text": f"[{content_prefix}] <som> {cleaned_content} <eom> [{' | '.join(content_suffix)}]"})
                else:
                    content_parts.append({"type": "text", "text": f"[{content_prefix}] <som> <eom>  [{ ' | '.join(content_suffix)}]"})

                # Add concurrently processed attachments
                content_parts.extend(processed_attachments_by_msg[msg_idx])

                if msg.embeds and _att_cfg.embeds.enabled:
                    for embed in msg.embeds:
                        parts = process_embed(embed)
                        content_parts.extend(parts)

                # Create message (using list format for content)
                # Add explicit speaker identification to help LLM distinguish between users
                if msg.author.bot:
                    result.append(AIMessage(content=content_parts))
                else:
                    # Include 'name' parameter to make speaker identity explicit
                    result.append(HumanMessage(
                        content=content_parts,
                        name=f"{msg.author.name}_{msg.author.id}"
                    ))

            return result
        except Exception as e:
            await func.report_error(e)
            return []
