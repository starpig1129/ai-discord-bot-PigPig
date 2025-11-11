"""Context manager that returns procedural context string and short-term LangChain messages.

This module implements the new ContextManager per docs/gpt/llms/context_manager.md:
- get_context returns Tuple[str, List[BaseMessage]]
- _format_context_for_prompt formats procedural memory only
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, List, Tuple

import discord

from function import func
from llm.memory.procedural import ProceduralMemoryProvider
from llm.memory.short_term import ShortTermMemoryProvider
from llm.memory.schema import ProceduralMemory
from langchain_core.messages import BaseMessage

_LOGGER = logging.getLogger(__name__)


class ContextManager:
    """Build procedural context string and return short-term messages list."""

    def __init__(
        self,
        short_term_provider: ShortTermMemoryProvider,
        procedural_provider: ProceduralMemoryProvider,
    ) -> None:
        """Initialize with memory providers."""
        self.short_term_provider = short_term_provider
        self.procedural_provider = procedural_provider

    async def get_context(self, message: discord.Message) -> Tuple[str, List[BaseMessage]]:
        """Return (procedural_context_str, short_term_msgs).

        The short_term_msgs are returned in oldest->newest order as produced by
        ShortTermMemoryProvider.
        """
        # 1) Fetch short-term messages
        try:
            short_term_msgs = await self.short_term_provider.get(message)
        except Exception as e:
            # Report and return safe fallback per design
            asyncio.create_task(
                func.report_error(e, "ContextManager.get_context: short_term_provider.get failed")
            )
            _LOGGER.exception("short_term_provider.get failed", exc_info=e)
            return "", []

        # 2) Extract user ids to fetch procedural memory
        try:
            user_ids = self._extract_user_ids_from_messages(short_term_msgs, message)
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "ContextManager.get_context: extract_user_ids failed")
            )
            _LOGGER.exception("extract_user_ids failed", exc_info=e)
            user_ids = []

        # 3) Fetch procedural memory (resilient: on failure continue with empty mapping)
        try:
            procedural_memory = await self.procedural_provider.get(user_ids)
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "ContextManager.get_context: procedural_provider.get failed")
            )
            _LOGGER.exception("procedural_provider.get failed", exc_info=e)
            procedural_memory = ProceduralMemory(user_info={})

        # 4) Format procedural memory into string (no STM serialization here)
        try:
            channel_name = getattr(message.channel, "name", str(getattr(message.channel, "id", "")))
        except Exception:
            channel_name = ""

        timestamp = datetime.utcnow().isoformat() + "Z"

        try:
            procedural_str = self._format_context_for_prompt(procedural_memory, channel_name, timestamp)
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "ContextManager.get_context: _format_context_for_prompt failed")
            )
            _LOGGER.exception("Formatting procedural context failed", exc_info=e)
            procedural_str = ""

        return procedural_str, short_term_msgs

    def _extract_user_ids_from_messages(self, messages: List[BaseMessage], message: discord.Message) -> List[str]:
        """Extract unique user ids from short-term messages and include message author.

        ShortTerm messages may not include explicit user ids. We attempt a best-effort
        extraction by parsing numeric ids in leading bracketed segments like "[123456]".
        """
        ids = set()

        # include incoming message author id if available
        try:
            if getattr(message, "author", None) is not None:
                aid = getattr(message.author, "id", None)
                if aid is not None:
                    ids.add(str(aid))
        except Exception:
            asyncio.create_task(
                func.report_error(Exception("failed to extract author id from message"),
                                  "ContextManager._extract_user_ids_from_messages/author")
            )

        # attempt to parse ids from BaseMessage.content
        try:
            for m in messages or []:
                try:
                    content = getattr(m, "content", "") or ""
                    match = re.match(r"^\[(?P<id>\d{4,})\]", content.strip())
                    if match:
                        ids.add(match.group("id"))
                except Exception:
                    # tolerate single message parse errors
                    continue
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "ContextManager._extract_user_ids_from_messages/iter")
            )
            _LOGGER.debug("Failed to iterate messages for id extraction", exc_info=e)

        return list(ids)

    def _format_context_for_prompt(self, procedural_memory: ProceduralMemory, channel_name: str, timestamp: str) -> str:
        """Format procedural memory and current state into a single string.

        This method intentionally does NOT serialize short-term memory; callers
        receive STM as LangChain messages separately.
        """
        parts: List[str] = ["--- System Context ---"]

        try:
            user_info_map = getattr(procedural_memory, "user_info", {}) or {}
            for uid, uinfo in user_info_map.items():
                sub_lines: List[str] = [f"User: {uid}"]
                if getattr(uinfo, "user_background", None):
                    sub_lines.append(f"Background: {uinfo.user_background}")
                if getattr(uinfo, "procedural_memory", None):
                    sub_lines.append(f"Preferences: {uinfo.procedural_memory}")
                parts.append("\n".join(sub_lines))
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "ContextManager._format_context_for_prompt/procedural")
            )
            _LOGGER.exception("Formatting procedural memory failed", exc_info=e)

        try:
            parts.append(f"Channel: #{channel_name}\nTimestamp: {timestamp}")
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "ContextManager._format_context_for_prompt/channel_ts")
            )
            _LOGGER.exception("Formatting channel/timestamp failed", exc_info=e)

        parts.append("--- End System Context ---")
        return "\n\n".join(parts)