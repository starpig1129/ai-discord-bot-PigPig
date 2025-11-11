"""Context manager for assembling SystemContext from memory providers.

This module implements the redesigned ContextManager per docs/plans/context_replan.md:
- No episodic provider maintained here.
- Procedural provider accepts a list of user_ids and returns a multi-user ProceduralMemory.
- All formatting for prompt insertion is encapsulated here; external callers should use get_context().
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Set

import discord

from function import func
from llm.memory.schema import SystemContext
from llm.memory.short_term import ShortTermMemoryProvider
from llm.memory.procedural import ProceduralMemoryProvider

_LOGGER = logging.getLogger(__name__)


class ContextManager:
    """Coordinator that builds a SystemContext and formats it for prompts.

    Public API:
    - async get_context(message: discord.Message) -> str
      Returns the final, formatted system context string ready to be injected
      into agent system prompts.
    """

    def __init__(
        self,
        short_term_provider: ShortTermMemoryProvider,
        procedural_provider: ProceduralMemoryProvider,
    ) -> None:
        """Initialize with necessary providers.

        Args:
            short_term_provider: Provider for recent message history.
            procedural_provider: Provider for user background / procedural memory.
        """
        self.short_term_provider = short_term_provider
        self.procedural_provider = procedural_provider

    async def build_context(self, message: discord.Message) -> SystemContext:
        """Gather short-term and procedural memory and assemble SystemContext.

        Behavior:
        1. await short_term_provider.get(message) -> ShortTermMemory
        2. extract unique user_ids from short_term messages (and include message.author)
        3. await procedural_provider.get(user_ids) -> ProceduralMemory
        4. return SystemContext(short_term_memory, procedural_memory, channel, timestamp)

        Errors are reported via func.report_error but do not raise to caller;
        the method attempts to return a usable SystemContext even on partial failures.
        """
        short_term_memory = None
        procedural_memory = None

        # 1) Get short term memory
        try:
            short_term_memory = await self.short_term_provider.get(message)
        except Exception as e:  # pragma: no cover - defensive error handling
            asyncio.create_task(
                func.report_error(e, "ContextManager.build_context: short_term_provider.get failed")
            )
            _LOGGER.exception("short_term_provider.get failed", exc_info=e)
            # Fallback to an object with messages attribute to keep downstream logic simple.
            short_term_memory = type("FallbackShortTerm", (), {"messages": []})()

        # 2) Extract unique user_ids from short term messages and message author
        try:
            user_ids = self._extract_user_ids_from_messages(short_term_memory.messages, message)
        except Exception as e:  # pragma: no cover - defensive
            asyncio.create_task(
                func.report_error(e, "ContextManager.build_context: extracting user_ids failed")
            )
            _LOGGER.exception("extract user ids failed", exc_info=e)
            user_ids = []

        # 3) Get procedural memory for the set of user_ids
        try:
            procedural_memory = await self.procedural_provider.get(user_ids)
        except Exception as e:  # pragma: no cover - defensive error handling
            asyncio.create_task(
                func.report_error(e, "ContextManager.build_context: procedural_provider.get failed")
            )
            _LOGGER.exception("procedural_provider.get failed", exc_info=e)
            # Fallback to an empty procedural memory representation if available on provider
            try:
                # If provider exposes an empty factory, use it; otherwise use simple empty mapping.
                procedural_memory = type("FallbackProcedural", (), {"user_info": {}})()
            except Exception:
                procedural_memory = type("FallbackProcedural", (), {"user_info": {}})()

        # 4) Build SystemContext
        try:
            channel_name = getattr(message.channel, "name", str(getattr(message.channel, "id", "")))
        except Exception:
            channel_name = ""

        # Prefer SystemContext dataclass constructor; if signature differs, rely on kwargs to fail fast.
        try:
            system_context = SystemContext(
                short_term_memory=short_term_memory,
                procedural_memory=procedural_memory,
                current_channel_name=channel_name,
            )
        except Exception as e:  # pragma: no cover - defensive
            asyncio.create_task(
                func.report_error(e, "ContextManager.build_context: SystemContext construction failed")
            )
            _LOGGER.exception("SystemContext construction failed", exc_info=e)
            # Minimal fallback object with expected attributes used by formatter.
            system_context = type(
                "FallbackSystemContext",
                (),
                {
                    "short_term_memory": short_term_memory,
                    "procedural_memory": procedural_memory,
                    "current_channel_name": channel_name,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            )()

        return system_context

    async def get_context(self, message: discord.Message) -> str:
        """Public method to obtain the fully formatted context string for prompts.

        This abstracts all internal memory fetching and formatting logic so callers
        (e.g. Orchestrator) only need to await this method and receive a string.
        """
        try:
            context = await self.build_context(message)
            formatted = self._format_context_for_prompt(context)
            return formatted
        except Exception as e:  # pragma: no cover - top-level defensive
            # Report and return empty string as a safe fallback.
            asyncio.create_task(func.report_error(e, "ContextManager.get_context failed"))
            _LOGGER.exception("ContextManager.get_context failed", exc_info=e)
            return ""

    def _extract_user_ids_from_messages(self, messages: List[Dict[str, Any]], message: discord.Message) -> List[str]:
        """Extract a de-duplicated list of user_ids from short-term messages and the incoming message.

        The short-term messages may be dictionaries with different shapes depending on
        storage/serialization. We attempt several common patterns but remain tolerant.
        """
        ids: Set[str] = set()

        # Include the immediate message author if present
        try:
            if getattr(message, "author", None) is not None:
                author = message.author
                # discord.Member or discord.User have .id
                aid = getattr(author, "id", None)
                if aid is not None:
                    ids.add(str(aid))
        except Exception:
            # non-fatal; report and continue
            asyncio.create_task(func.report_error(Exception("failed to extract author id from message"), "ContextManager._extract_user_ids_from_messages/author"))

        # Iterate stored messages
        if not messages:
            return list(ids)

        for m in messages:
            try:
                # If message is a mapping-like object
                if isinstance(m, dict):
                    # common fields
                    for key in ("author_id", "user_id", "authorId", "author"):
                        if key in m and m[key] is not None:
                            # If author is a dict or object with id
                            val = m[key]
                            if isinstance(val, dict) and "id" in val:
                                ids.add(str(val["id"]))
                                break
                            # If author stored as object with id attribute
                            if hasattr(val, "id"):
                                ids.add(str(getattr(val, "id")))
                                break
                            ids.add(str(val))
                            break
                    else:
                        # try nested author structure
                        author_field = m.get("author")
                        if isinstance(author_field, dict) and "id" in author_field:
                            ids.add(str(author_field["id"]))
                else:
                    # If stored as an object with author attribute
                    author = getattr(m, "author", None)
                    if author is not None and hasattr(author, "id"):
                        ids.add(str(getattr(author, "id")))
            except Exception as e:  # pragma: no cover - tolerate malformed message entries
                asyncio.create_task(func.report_error(e, "ContextManager._extract_user_ids_from_messages/iter"))
                _LOGGER.debug("Failed to parse message entry for user id: %s", m, exc_info=e)

        return list(ids)

    def _format_context_for_prompt(self, context: SystemContext) -> str:
        """Convert a SystemContext into the final string inserted into system prompts.

        Format specification (per docs/plans/context_replan.md):
        - Header and footer markers.
        - For each user in procedural_memory.user_info, emit a subsection containing:
          - User id
          - Background if present (uinfo.user_background)
          - Preferences / procedural memory if present (uinfo.procedural_memory)
        - Recent short-term messages, time-ordered, as: [timestamp] author: content
        - Channel and system timestamp
        """
        parts: List[str] = ["--- System Context ---"]

        # Procedural memory: iterate user_info mapping if present
        proc = getattr(context, "procedural_memory", None)
        try:
            user_info_map = getattr(proc, "user_info", {}) if proc is not None else {}
            for uid, uinfo in user_info_map.items():
                sub_lines: List[str] = [f"User: {uid}"]
                # user_background attribute optional
                if getattr(uinfo, "user_background", None):
                    sub_lines.append(f"Background: {uinfo.user_background}")
                # procedural_memory / preferences optional
                if getattr(uinfo, "procedural_memory", None):
                    sub_lines.append(f"Preferences: {uinfo.procedural_memory}")
                parts.append("\n".join(sub_lines))
        except Exception as e:  # pragma: no cover - defensive
            asyncio.create_task(func.report_error(e, "ContextManager._format_context_for_prompt/procedural"))
            _LOGGER.exception("Formatting procedural memory failed", exc_info=e)

        # Short-term messages
        stm = getattr(context, "short_term_memory", None)
        try:
            msgs = getattr(stm, "messages", []) if stm is not None else []
            if msgs:
                # Attempt to sort by timestamp if available
                def _msg_timestamp_key(m: Dict[str, Any]):
                    for k in ("timestamp", "time", "ts"):
                        if isinstance(m, dict) and k in m and m[k]:
                            return m[k]
                        # object-like message may have attribute
                        if hasattr(m, k):
                            return getattr(m, k)
                    # fallback: empty string sorts first
                    return ""

                try:
                    msgs_sorted = sorted(msgs, key=_msg_timestamp_key)
                except Exception:
                    msgs_sorted = list(msgs)

                msg_lines: List[str] = []
                for m in msgs_sorted:
                    try:
                        # resolve timestamp, author display name, and content robustly
                        ts = (
                            (m.get("timestamp") if isinstance(m, dict) else getattr(m, "timestamp", None))
                            or (getattr(context, "timestamp", None))
                            or ""
                        )
                        author = ""
                        content = ""
                        if isinstance(m, dict):
                            author = m.get("author_display") or m.get("author") or m.get("author_name") or m.get("author_id") or ""
                            # if author is object-like dict
                            if isinstance(author, dict) and "name" in author:
                                author = author["name"]
                            content = m.get("content") or m.get("text") or m.get("msg") or ""
                        else:
                            author_obj = getattr(m, "author", None)
                            if author_obj is not None:
                                author = getattr(author_obj, "display_name", None) or getattr(author_obj, "name", None) or str(getattr(author_obj, "id", ""))
                            content = getattr(m, "content", "") or getattr(m, "text", "") or ""
                        msg_lines.append(f"[{ts}] {author}: {content}")
                    except Exception as e:  # pragma: no cover - tolerate single message formatting failure
                        asyncio.create_task(func.report_error(e, "ContextManager._format_context_for_prompt/format_msg"))
                        _LOGGER.debug("Failed to format short-term message: %s", m, exc_info=e)
                if msg_lines:
                    parts.append("Recent Conversation:\n" + "\n".join(msg_lines))
        except Exception as e:  # pragma: no cover - defensive
            asyncio.create_task(func.report_error(e, "ContextManager._format_context_for_prompt/short_term"))
            _LOGGER.exception("Formatting short term memory failed", exc_info=e)

        # Current channel and timestamp
        try:
            channel = getattr(context, "current_channel_name", "")
            timestamp = getattr(context, "timestamp", None) or datetime.utcnow().isoformat() + "Z"
            parts.append(f"Channel: #{channel}\nTimestamp: {timestamp}")
        except Exception as e:  # pragma: no cover - defensive
            asyncio.create_task(func.report_error(e, "ContextManager._format_context_for_prompt/channel_ts"))
            _LOGGER.exception("Formatting channel/timestamp failed", exc_info=e)

        parts.append("--- End System Context ---")
        return "\n\n".join(parts)