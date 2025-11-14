# cogs/memory/services/vectorization_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from function import func
from addons.settings import MemoryConfig
from cogs.memory.interfaces.vector_store_interface import MemoryFragment
from cogs.memory.interfaces.storage_interface import StorageInterface
from .event_summarization_service import EventSummarizationService, EventSummary

import discord

logger = logging.getLogger(__name__)


class VectorizationService:
    """
    Service responsible for converting stored messages into MemoryFragment objects,
    uploading them to the vector store, and applying the configured data retention
    policy (archive / delete / none).

    Dependencies are injected to keep this service testable and decoupled:
      - bot: used only for contextual logging if needed
      - storage: implements StorageInterface
      - vector_manager: object that exposes .store.add_memories(...)
      - settings: MemoryConfig (should contain data_retention_policy and optional batch size)
    """

    def __init__(
        self,
        bot: Any,
        storage: StorageInterface,
        vector_manager: Any,
        settings: MemoryConfig,
    ) -> None:
        self.bot = bot
        self.storage = storage
        self.vector_manager = vector_manager
        self.settings = settings
        self.event_summarization_service = EventSummarizationService(bot, settings)

    async def _get_unprocessed_message_objects(self, message_ids: Optional[List[int]] = None) -> List[discord.Message]:
        """
        Try to get unprocessed discord.Message objects.
        
        Args:
            message_ids: Optional list of message_id integers to restrict processing to.
            
        Returns:
            List of discord.Message objects or empty list if not available.
        """
        try:
            # Try to use a method that returns discord.Message objects
            # This might not be implemented in all storage backends
            get_messages_method = getattr(self.storage, "get_unprocessed_message_objects", None)
            if get_messages_method:
                if message_ids:
                    limit = max(1, len(message_ids))
                    return await get_messages_method(limit=limit, message_ids=message_ids)
                else:
                    limit = getattr(self.settings, "vector_batch_size", None)
                    if limit is None:
                        limit = getattr(self.settings, "vectorization_batch_size", 100)
                    return await get_messages_method(limit=limit)
            else:
                logger.debug("get_unprocessed_message_objects method not available in storage backend")
                return []
        except Exception as e:
            logger.debug(f"Failed to get message objects: {e}")
            return []

    async def process_unvectorized_messages(
        self,
        message_ids: Optional[List[int]] = None,
        messages: Optional[List[discord.Message]] = None
    ) -> None:
        """
        Main entrypoint for processing unvectorized messages using EventSummarizationService.

        Args:
            message_ids: Optional list of message_id integers to restrict processing to.
                         If omitted, a batch of unprocessed messages will be retrieved
                         from storage.
            messages: Optional list of discord.Message objects provided directly by caller.
                      When present, these messages are used instead of querying the storage
                      backend for message objects.
        """
        try:
            if not self.storage:
                raise ValueError("storage dependency is required for VectorizationService")

            if not self.vector_manager:
                raise ValueError("vector_manager dependency is required for VectorizationService")

            # If caller provided discord.Message objects directly, use them.
            if messages is not None:
                discord_messages = messages
                logger.debug(f"process_unvectorized_messages: received {len(discord_messages)} messages from caller")
            else:
                # Try to get discord.Message objects for event summarization from storage backend
                discord_messages = await self._get_unprocessed_message_objects(message_ids)

            if discord_messages:
                # Use EventSummarizationService to process messages
                logger.info(f"Processing {len(discord_messages)} messages with EventSummarizationService")
                event_summaries = await self.event_summarization_service.summarize_events(discord_messages)

                if not event_summaries:
                    logger.debug("No event summaries generated from messages")
                    return

                # Convert EventSummary objects to MemoryFragment objects
                fragments = await self._convert_event_summaries_to_fragments(event_summaries)
                # Collect all message IDs for the range covered by each event
                message_id_list = []
                for event_summary in event_summaries:
                    # Add all message IDs in the range from start to end
                    start_id = event_summary.metadata.start_message_id
                    end_id = event_summary.metadata.end_message_id
                    if start_id <= end_id:
                        message_id_list.extend(range(start_id, end_id + 1))
                    else:
                        message_id_list.extend(range(end_id, start_id + 1))

            else:
                # Fallback to original row-based processing if discord.Message objects not available
                logger.debug("Using fallback row-based processing")
                fragments, message_id_list = await self._process_rows_fallback(message_ids)

            if not fragments:
                logger.debug("No memory fragments created")
                return

            # Ensure vector manager store is ready
            store = getattr(self.vector_manager, "store", None)
            if store is None:
                raise RuntimeError("vector_manager.store is not initialized")

            # Upload fragments to vector store
            try:
                await store.add_memories(fragments)
            except Exception as e:
                await func.report_error(e, "vector_store_add_memories_failed")
                return

            # Mark messages as vectorized in storage
            try:
                await self.storage.mark_messages_vectorized(message_id_list)
            except Exception as e:
                await func.report_error(e, "mark_messages_vectorized_failed")
            
            # Apply data retention policy from settings
            policy = getattr(self.settings, "data_retention_policy", None)
            if isinstance(policy, str):
                policy = policy.lower().strip()

            if policy == "archive":
                try:
                    await self.storage.archive_messages(message_id_list)
                except Exception as e:
                    await func.report_error(e, "archive_messages_failed")
            elif policy == "delete":
                try:
                    delete_method = getattr(self.storage, "delete_messages", None)
                    if not delete_method:
                        raise AttributeError("Storage backend does not implement delete_messages")
                    await delete_method(message_id_list)
                except Exception as e:
                    await func.report_error(e, "delete_messages_failed")
            else:
                logger.debug("Data retention policy set to 'none' or unspecified; skipping archive/delete.")

        except Exception as e:
            logger.exception("Unexpected error in VectorizationService.process_unvectorized_messages: %s", e)
            await func.report_error(e, "vectorization_service_general_error")

    async def _convert_event_summaries_to_fragments(self, event_summaries: List[EventSummary]) -> List[MemoryFragment]:
        """
        Convert EventSummary objects to MemoryFragment objects.
        
        Args:
            event_summaries: List of EventSummary objects from EventSummarizationService
            
        Returns:
            List of MemoryFragment objects
        """
        fragments = []
        
        for event_summary in event_summaries:
            try:
                # Create metadata from EventSummary
                metadata = {
                    "fragment_id": f"event-{event_summary.metadata.start_message_id}",
                    "source_message_ids": list(range(
                        event_summary.metadata.start_message_id,
                        event_summary.metadata.end_message_id + 1
                    )),
                    "jump_url": f"https://discord.com/channels/{event_summary.metadata.guild_id}/{event_summary.metadata.channel_id}/{event_summary.metadata.start_message_id}",
                    "author_ids": [str(uid) for uid in event_summary.metadata.user_ids],
                    "channel_id": str(event_summary.metadata.channel_id),
                    "guild_id": str(event_summary.metadata.guild_id),
                    "start_timestamp": event_summary.metadata.start_timestamp,
                    "end_timestamp": event_summary.metadata.end_timestamp,
                    "reactions_json": json.dumps(event_summary.metadata.reaction_list),
                    "event_type": event_summary.metadata.event_type or "conversation",
                }
                
                frag = MemoryFragment(
                    id=str(event_summary.metadata.start_message_id),
                    content=event_summary.query_value,
                    query_key=event_summary.query_key,
                    metadata=metadata,
                )
                fragments.append(frag)
                
            except Exception as e:
                logger.error(f"Failed to convert event summary to fragment: {e}")
                await func.report_error(e, "event_summary_to_fragment_conversion_failed")
                continue
        
        return fragments

    async def _process_rows_fallback(self, message_ids: Optional[List[int]] = None) -> tuple[List[MemoryFragment], List[int]]:
        """
        Fallback processing using database rows when discord.Message objects are not available.
        
        Args:
            message_ids: Optional list of message_id integers to restrict processing to.
            
        Returns:
            Tuple of (fragments, message_id_list)
        """
        # Determine batch of messages to process
        messages_to_process: List[Dict[str, Any]] = []
        if message_ids:
            limit = max(1, len(message_ids))
            rows = await self.storage.get_unprocessed_messages(limit=limit)
            id_set = set(int(i) for i in message_ids if i is not None)
            def safe_int_conversion(value):
                try:
                    if value is None:
                        return None
                    if isinstance(value, int):
                        return value
                    if isinstance(value, str) and value.isdigit():
                        return int(value)
                    return None
                except (ValueError, TypeError):
                    return None
            
            messages_to_process = [r for r in rows if safe_int_conversion(r.get("message_id")) in id_set]
        else:
            limit = getattr(self.settings, "vector_batch_size", None)
            if limit is None:
                limit = getattr(self.settings, "vectorization_batch_size", 100)
            messages_to_process = await self.storage.get_unprocessed_messages(limit=limit)

        if not messages_to_process:
            return [], []

        # Convert rows into MemoryFragment objects
        fragments: List[MemoryFragment] = []
        message_id_list: List[int] = []
        
        for row in messages_to_process:
            try:
                message_id_value = row.get("message_id")
                if message_id_value is None:
                    continue
                if isinstance(message_id_value, int):
                    mid = message_id_value
                elif isinstance(message_id_value, str) and message_id_value.isdigit():
                    mid = int(message_id_value)
                else:
                    await func.report_error(ValueError(f"Invalid message_id in row: {row}"), "vectorization_invalid_row")
                    continue
            except Exception:
                await func.report_error(ValueError(f"Invalid message_id in row: {row}"), "vectorization_invalid_row")
                continue

            content = row.get("content", "") or ""
            query_key = content
            
            # Safe timestamp conversion
            timestamp_value = row.get("timestamp")
            try:
                if timestamp_value is None:
                    timestamp = None
                elif isinstance(timestamp_value, (int, float)):
                    timestamp = float(timestamp_value)
                elif isinstance(timestamp_value, str):
                    timestamp = float(timestamp_value)
                else:
                    timestamp = None
            except (ValueError, TypeError):
                timestamp = None
            
            metadata: Dict[str, Any] = {
                "fragment_id": f"msg-{mid}",
                "source_message_ids": [mid],
                "jump_url": None,
                "author_id": str(row.get("user_id")) if row.get("user_id") is not None else None,
                "channel_id": str(row.get("channel_id")) if row.get("channel_id") is not None else None,
                "guild_id": str(row.get("guild_id")) if row.get("guild_id") is not None else None,
                "timestamp": timestamp,
                "reactions_json": json.dumps(row.get("reactions")) if row.get("reactions") is not None else None,
            }

            # Build jump_url
            try:
                if metadata["guild_id"] is not None and metadata["channel_id"] is not None:
                    metadata["jump_url"] = (
                        f"https://discord.com/channels/{metadata['guild_id']}/{metadata['channel_id']}/{mid}"
                    )
            except Exception:
                metadata["jump_url"] = None

            frag = MemoryFragment(
                id=str(mid),
                content=content,
                query_key=query_key,
                metadata=metadata,
            )
            fragments.append(frag)
            message_id_list.append(mid)

        return fragments, message_id_list