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

    async def process_unvectorized_messages(self, message_ids: Optional[List[int]] = None) -> None:
        """
        Main entrypoint.

        Args:
            message_ids: Optional list of message_id integers to restrict processing to.
                         If omitted, a batch of unprocessed messages will be retrieved
                         from storage.get_unprocessed_messages(limit=...).
        """
        try:
            if not self.storage:
                raise ValueError("storage dependency is required for VectorizationService")

            if not self.vector_manager:
                raise ValueError("vector_manager dependency is required for VectorizationService")

            # Determine batch of messages to process
            messages_to_process: List[Dict[str, Any]] = []
            if message_ids:
                # Fetch a batch of unprocessed messages and filter by provided ids.
                # We cannot rely on a storage method to fetch arbitrary ids (not in interface),
                # so request a batch sized to the number of ids and filter locally.
                limit = max(1, len(message_ids))
                rows = await self.storage.get_unprocessed_messages(limit=limit)
                # Filter only rows whose message_id is in the provided list.
                id_set = set(int(i) for i in message_ids)
                messages_to_process = [r for r in rows if int(r.get("message_id")) in id_set]
            else:
                # Determine batch size from settings if available; otherwise, use 100.
                limit = getattr(self.settings, "vector_batch_size", None)
                if limit is None:
                    limit = getattr(self.settings, "vectorization_batch_size", 100)
                messages_to_process = await self.storage.get_unprocessed_messages(limit=limit)

            if not messages_to_process:
                logger.debug("No unvectorized messages found to process.")
                return

            # Convert rows into MemoryFragment objects
            fragments: List[MemoryFragment] = []
            message_id_list: List[int] = []
            for row in messages_to_process:
                try:
                    mid = int(row.get("message_id"))
                except Exception:
                    # skip malformed rows but report
                    await func.report_error(ValueError(f"Invalid message_id in row: {row}"), "vectorization_invalid_row")
                    continue

                content = row.get("content", "") or ""
                query_key = content  # simple choice: use content as query key; more advanced LLM summarization can be added later
                metadata: Dict[str, Any] = {
                    "fragment_id": f"msg-{mid}",
                    "source_message_ids": [mid],
                    "jump_url": None,
                    "author_id": str(row.get("user_id")) if row.get("user_id") is not None else None,
                    "channel_id": str(row.get("channel_id")) if row.get("channel_id") is not None else None,
                    "guild_id": str(row.get("guild_id")) if row.get("guild_id") is not None else None,
                    "timestamp": float(row.get("timestamp")) if row.get("timestamp") is not None else None,
                    "reactions_json": json.dumps(row.get("reactions")) if row.get("reactions") is not None else None,
                }

                # Build jump_url when guild/channel/message ids exist
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

            if not fragments:
                logger.debug("No valid memory fragments created from rows.")
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
                # Do not proceed to mark vectorized if upload failed
                return

            # Mark messages as vectorized in storage
            try:
                await self.storage.mark_messages_vectorized(message_id_list)
            except Exception as e:
                await func.report_error(e, "mark_messages_vectorized_failed")
                # Continue to retention step even if marking failed; retention assumes vectorization happened.
            
            # Apply data retention policy from settings
            policy = getattr(self.settings, "data_retention_policy", None)
            # Normalize policy to lower-case for comparison
            if isinstance(policy, str):
                policy = policy.lower().strip()

            if policy == "archive":
                try:
                    await self.storage.archive_messages(message_id_list)
                except Exception as e:
                    await func.report_error(e, "archive_messages_failed")
            elif policy == "delete":
                # StorageInterface was extended to include delete_messages
                try:
                    delete_method = getattr(self.storage, "delete_messages", None)
                    if not delete_method:
                        raise AttributeError("Storage backend does not implement delete_messages")
                    await delete_method(message_id_list)
                except Exception as e:
                    await func.report_error(e, "delete_messages_failed")
            else:
                # 'none' or unspecified: do nothing
                logger.debug("Data retention policy set to 'none' or unspecified; skipping archive/delete.")

        except Exception as e:
            logger.exception("Unexpected error in VectorizationService.process_unvectorized_messages: %s", e)
            await func.report_error(e, "vectorization_service_general_error")