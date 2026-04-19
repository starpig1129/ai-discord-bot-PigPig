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
from llm.memory.knowledge import KnowledgeMemoryProvider, KnowledgeMemory
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
        knowledge_provider: Optional[KnowledgeMemoryProvider] = None,
    ) -> None:
        """Initialize with memory providers."""
        self.short_term_provider = short_term_provider
        self.procedural_provider = procedural_provider
        self.episodic_provider = episodic_provider
        self.knowledge_provider = knowledge_provider

    async def get_context(self, message: discord.Message) -> Tuple[str, List[BaseMessage]]:
        """Return (procedural_context_str, short_term_msgs).

        The short_term_msgs are returned in oldest->newest order as produced by
        ShortTermMemoryProvider.
        """

        async def _fetch_short_term_and_procedural() -> Tuple[ProceduralMemory, List[BaseMessage]]:
            # 0) Concurrently pre-fetch author's procedural memory to warm cache
            author_id_str = None
            try:
                author_id = getattr(getattr(message, "author", None), "id", None)
                if author_id is not None:
                    author_id_str = str(author_id)
            except Exception:
                pass

            prefetch_task = None
            if author_id_str:
                prefetch_task = asyncio.create_task(self.procedural_provider.get([author_id_str]))

            # 1) Fetch short-term messages
            short_term_msgs: List[BaseMessage] = []
            try:
                short_term_msgs = await self.short_term_provider.get(message)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Report and continue with safe fallback per design
                asyncio.create_task(
                    func.report_error(e, "ContextManager.get_context: short_term_provider.get failed")
                )
                _LOGGER.error("short_term_provider.get failed", exception=e)

            # 2) Extract user ids to fetch procedural memory
            try:
                user_ids = self._extract_user_ids_from_messages(short_term_msgs, message)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                asyncio.create_task(
                    func.report_error(e, "ContextManager.get_context: extract_user_ids failed")
                )
                _LOGGER.error("extract_user_ids failed", exception=e)
                user_ids = []
                try:
                    fallback_author_id = getattr(getattr(message, "author", None), "id", None)
                    if fallback_author_id is not None:
                        user_ids.append(str(fallback_author_id))
                except Exception:
                    # Best-effort fallback; proceed with empty user_ids
                    pass

            # Await the prefetch task to ensure the cache is warmed
            if prefetch_task:
                try:
                    await prefetch_task
                except Exception:
                    pass # ignore prefetch errors, will be caught in final get

            # 3) Fetch procedural memory
            try:
                procedural_memory = await self.procedural_provider.get(user_ids)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                asyncio.create_task(
                    func.report_error(e, "ContextManager.get_context: procedural_provider.get failed")
                )
                _LOGGER.error("procedural_provider.get failed", exception=e)
                procedural_memory = ProceduralMemory(user_info={})

            return procedural_memory, short_term_msgs


        async def _fetch_episodic() -> Optional[str]:
            if not self.episodic_provider:
                return None
            try:
                return await self.episodic_provider.get(message)
            except asyncio.CancelledError:
                return None
            except Exception as e:
                asyncio.create_task(
                    func.report_error(e, "ContextManager.get_context: episodic_provider.get failed")
                )
                _LOGGER.error("episodic_provider.get failed", exception=e)
                return None

        async def _fetch_knowledge() -> Optional[KnowledgeMemory]:
            if not self.knowledge_provider:
                return None
            try:
                guild_id = str(message.guild.id) if message.guild else None
                channel_id = str(message.channel.id)
                return await self.knowledge_provider.get(guild_id, channel_id)
            except asyncio.CancelledError:
                return None
            except Exception as e:
                asyncio.create_task(
                    func.report_error(e, "ContextManager.get_context: knowledge_provider.get failed")
                )
                _LOGGER.error("knowledge_provider.get failed", exception=e)
                return None

        # Fetch all memory components in parallel to minimize latency
        (procedural_memory, short_term_msgs), episodic_str, knowledge = await asyncio.gather(
            _fetch_short_term_and_procedural(),
            _fetch_episodic(),
            _fetch_knowledge(),
        )

        # 4) Format procedural memory into string (no STM serialization here)
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
                procedural_memory, 
                channel_name, 
                timestamp, 
                episodic_str=episodic_str, 
                human_time=human_time,
                knowledge=knowledge
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
        knowledge: Optional[KnowledgeMemory] = None,
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

        if knowledge:
            if knowledge.guild_knowledge:
                parts.append(f"--- Guild Knowledge ---\n{knowledge.guild_knowledge}")
            if knowledge.channel_knowledge:
                parts.append(f"--- Channel Knowledge (Inside Jokes) ---\n{knowledge.channel_knowledge}")

        parts.append("--- End System Context ---")
        return "\n\n".join(parts)
