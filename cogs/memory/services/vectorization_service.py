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
from .event_summarization_service import EventSummary

logger = logging.getLogger(__name__)


class VectorizationService:
    """
    Service responsible for converting EventSummary objects into MemoryFragment objects,
    uploading them to the vector store.
    
    Dependencies are injected to keep this service testable and decoupled:
      - bot: used only for contextual logging if needed
      - storage: implements StorageInterface
      - vector_manager: object that exposes .store.add_memories(...)
      - settings: MemoryConfig
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

    async def process_event_summaries(self, event_summaries: List[EventSummary]) -> None:
        """
        Process a list of EventSummary objects and store them in the vector database.
        
        Args:
            event_summaries: List of EventSummary objects to process and store
            
        Returns:
            None
        """
        try:
            if not self.storage:
                raise ValueError("storage dependency is required for VectorizationService")

            if not self.vector_manager:
                raise ValueError("vector_manager dependency is required for VectorizationService")

            if not event_summaries:
                logger.debug("No event summaries provided for processing")
                return

            # Convert EventSummary objects to MemoryFragment objects
            logger.info(f"Converting {len(event_summaries)} event summaries to memory fragments")
            fragments = await self._convert_event_summaries_to_fragments(event_summaries)

            if not fragments:
                logger.debug("No memory fragments created from event summaries")
                return

            # Ensure vector manager store is ready
            store = getattr(self.vector_manager, "store", None)
            if store is None:
                raise RuntimeError("vector_manager.store is not initialized")

            # Upload fragments to vector store
            try:
                logger.info(f"Storing {len(fragments)} memory fragments in vector database")
                await store.add_memories(fragments)
                logger.info("Successfully stored memory fragments in vector database")
            except Exception as e:
                await func.report_error(e, "vector_store_add_memories_failed")
                return

        except Exception as e:
            logger.exception("Unexpected error in VectorizationService.process_event_summaries: %s", e)
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
                    "source_message_ids": [event_summary.metadata.start_message_id, event_summary.metadata.end_message_id],
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