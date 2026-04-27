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
            history = [
                msg async for msg in message.channel.history(limit=self.limit)
            ]
            history.reverse()

            result: List[BaseMessage] = []
            for msg in history:
                content_parts = []
                content_suffix = []

                content_prefix = f"{msg.author.name} | UserID:{msg.author.id} | MessageID:{msg.id}"
                                # Include embed count if present

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
                            ref_content = "[圖片/附件]"
                        ref_text = f"回覆給 @{ref_author}: '{ref_content}' (MessageID:{msg.reference.message_id})"
                        
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

                if msg.attachments:
                    for attachment in msg.attachments:
                        if attachment.content_type:
                            if attachment.content_type.startswith('image/'):
                                # Standard LangChain format for both Gemini and Ollama
                                content_parts.append({
                                    "type": "image_url",
                                    "image_url": {"url": attachment.url}
                                })
                            elif attachment.content_type.startswith('video/'):
                                content_parts.append({
                                    "type": "text",
                                    "text": f"[影片附件: {attachment.filename}]"
                                })
                            elif attachment.content_type == 'application/pdf':
                                content_parts.append({
                                    "type": "text",
                                    "text": f"[PDF 附件: {attachment.filename}]"
                                })
                            elif attachment.content_type.startswith('audio/'):
                                content_parts.append({
                                    "type": "text",
                                    "text": f"[音訊附件: {attachment.filename}]"
                                })

                # 創建消息（使用列表格式的 content）
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
