"""Context manager that returns procedural context string and short-term LangChain messages.

This module implements the new ContextManager per docs/llm/context_manager.md:
- get_context returns Tuple[str, List[BaseMessage]]
- _format_context_for_prompt formats procedural memory only
"""

import asyncio

import re
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

import discord

from function import func
from llm.memory.procedural import ProceduralMemoryProvider
from llm.memory.short_term import ShortTermMemoryProvider
from llm.memory.episodic import EpisodicMemoryProvider
from llm.memory.schema import ProceduralMemory
from langchain_core.messages import BaseMessage
from addons.logging import get_logger

_LOGGER = get_logger(server_id="Bot", source="llm.context_manager")


class ContextManager:
    """Build procedural context string and return short-term messages list."""

    def __init__(
        self,
        short_term_provider: ShortTermMemoryProvider,
        procedural_provider: ProceduralMemoryProvider,
        episodic_provider: Optional[EpisodicMemoryProvider] = None,
    ) -> None:
        """Initialize with memory providers."""
        self.short_term_provider = short_term_provider
        self.procedural_provider = procedural_provider
        self.episodic_provider = episodic_provider

    async def get_context(self, message: discord.Message) -> Tuple[str, List[BaseMessage]]:
        """Return (procedural_context_str, short_term_msgs).

        The short_term_msgs are returned in oldest->newest order as produced by
        ShortTermMemoryProvider.
        """

        async def _fetch_short_term() -> List[BaseMessage]:
            try:
                return await self.short_term_provider.get(message)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                asyncio.create_task(
                    func.report_error(e, "ContextManager.get_context: short_term_provider.get failed")
                )
                _LOGGER.error("short_term_provider.get failed", exception=e)
                return []

        async def _fetch_episodic() -> Optional[str]:
            if not self.episodic_provider:
                return None
            try:
                return await self.episodic_provider.get(message)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                asyncio.create_task(
                    func.report_error(e, "ContextManager.get_context: episodic_provider.get failed")
                )
                _LOGGER.error("episodic_provider.get failed", exception=e)
                return None

        async def _fetch_procedural(uids: List[str]) -> ProceduralMemory:
            if not uids:
                return ProceduralMemory(user_info={})
            try:
                return await self.procedural_provider.get(uids)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                asyncio.create_task(
                    func.report_error(e, "ContextManager.get_context: procedural_provider.get failed")
                )
                _LOGGER.error("procedural_provider.get failed", exception=e)
                return ProceduralMemory(user_info={})

        # 1. Extract author ID to start their procedural memory fetch immediately
        author_ids = []
        try:
            fallback_author_id = getattr(getattr(message, "author", None), "id", None)
            if fallback_author_id is not None:
                author_ids.append(str(fallback_author_id))
        except Exception:
            pass

        # 2. Fetch short-term, episodic, and author procedural memory in parallel
        short_term_msgs, episodic_str, author_procedural = await asyncio.gather(
            _fetch_short_term(),
            _fetch_episodic(),
            _fetch_procedural(author_ids),
        )

        # 3. Extract any additional user IDs from the fetched short-term messages
        try:
            extracted_ids = self._extract_user_ids_from_messages(short_term_msgs, message)
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "ContextManager.get_context: extract_user_ids failed")
            )
            _LOGGER.error("extract_user_ids failed", exception=e)
            extracted_ids = []

        # 4. Fetch procedural memory for any additional users
        additional_ids = [uid for uid in extracted_ids if uid not in author_ids]
        if additional_ids:
            additional_procedural = await _fetch_procedural(additional_ids)
            # Merge procedural memories
            merged_info = dict(getattr(author_procedural, "user_info", {}))
            merged_info.update(getattr(additional_procedural, "user_info", {}))
            procedural_memory = ProceduralMemory(user_info=merged_info)
        else:
            procedural_memory = author_procedural

        # 5) Format procedural memory into string (no STM serialization here)
        try:
            channel_name = getattr(message.channel, "name", str(getattr(message.channel, "id", "")))
        except Exception:
            channel_name = ""

        # Use message.created_at when available; fallback to current UTC timestamp (float seconds)
        try:
            if getattr(message, "created_at", None) is not None:
                created_at = message.created_at
                if getattr(created_at, "tzinfo", None) is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                else:
                    created_at = created_at.astimezone(timezone.utc)
                timestamp = created_at.timestamp()
                human_time = created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
            else:
                now = datetime.now(timezone.utc)
                timestamp = now.timestamp()
                human_time = now.strftime('%Y-%m-%d %H:%M:%S UTC')
        except Exception:
            now = datetime.now(timezone.utc)
            timestamp = now.timestamp()
            human_time = now.strftime('%Y-%m-%d %H:%M:%S UTC')

        procedural_str = ""
        try:
            procedural_str = self._format_context_for_prompt(
                procedural_memory, channel_name, timestamp, episodic_str=episodic_str, human_time=human_time
            )
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "ContextManager.get_context: _format_context_for_prompt failed")
            )
            _LOGGER.error("Formatting procedural context failed", exception=e)

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
                    msg_name = getattr(m, "name", None)
                    if isinstance(msg_name, str):
                        for match in re.findall(r"(\d{4,})", msg_name):
                            ids.add(match)

                    content = getattr(m, "content", None)
                    candidate_texts: List[str] = []
                    if isinstance(content, str):
                        candidate_texts.append(content)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict):
                                text_val = part.get("text")
                                if isinstance(text_val, str):
                                    candidate_texts.append(text_val)
                            elif isinstance(part, str):
                                candidate_texts.append(part)

                    for text in candidate_texts:
                        for match in re.findall(r"UserID:(\d+)", text):
                            ids.add(match)
                        bracket_match = re.match(r"^\[(?P<id>\d{4,})\]", text.strip())
                        if bracket_match:
                            ids.add(bracket_match.group("id"))
                except Exception:
                    # tolerate single message parse errors
                    continue
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "ContextManager._extract_user_ids_from_messages/iter")
            )
            _LOGGER.debug("Failed to iterate messages for id extraction", exception=e)

        return list(ids)

    def _format_context_for_prompt(
        self,
        procedural_memory: ProceduralMemory,
        channel_name: str,
        timestamp: float,
        episodic_str: Optional[str] = None,
        human_time: Optional[str] = None,
    ) -> str:
        """Format procedural memory and current state into a single string.
 
        This method intentionally does NOT serialize short-term memory; callers
        receive STM as LangChain messages separately.
        The `timestamp` parameter is a numeric UNIX timestamp (float seconds). If a
        human-readable form is needed, callers should format it explicitly.
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
            _LOGGER.error("Formatting procedural memory failed", exception=e)

        try:
            # Provide both Unix timestamp and human-readable time for better LLM comprehension
            if human_time:
                parts.append(f"Channel: #{channel_name}\nTimestamp: {timestamp}\nCurrent Time: {human_time}")
            else:
                parts.append(f"Channel: #{channel_name}\nTimestamp: {timestamp}")
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "ContextManager._format_context_for_prompt/channel_ts")
            )
            _LOGGER.error("Formatting channel/timestamp failed", exception=e)

        if episodic_str:
            parts.append(episodic_str)

        parts.append("--- End System Context ---")
        return "\n\n".join(parts)
