# cogs/memory/services/episodic_memory_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from function import func
from addons.settings import memory_config, MemoryConfig
from cogs.memory.interfaces.storage_interface import StorageInterface
from cogs.memory.services.message_tracker import MessageTracker

if TYPE_CHECKING:
    from bot import PigPig

log = logging.getLogger(__name__)


class EpisodicMemoryService(commands.Cog):
    """
    A background service responsible for the first stage of the ETL process
    for episodic memory. It fetches full message objects from Discord's API
    based on pending messages tracked by the MessageTracker.
    """

    def __init__(self, bot: "PigPig", storage: "StorageInterface" = None):
        """
        Args:
            bot (PigPig): The bot instance.
            storage (StorageInterface): Storage backend implementing StorageInterface.
                                       If None, will fall back to bot.db_manager for backward compatibility.
        """
        self.bot: "PigPig" = bot
        # Accept a StorageInterface; allow fallback to bot.db_manager for compatibility.
        self.storage: StorageInterface = storage if storage is not None else getattr(bot, "db_manager", None)
        self.settings: MemoryConfig = memory_config
        self.message_tracker: MessageTracker = getattr(self.bot, "message_tracker", None)
        self.is_processing = False

    async def cog_load(self) -> None:
        """Starts the background task when the cog is loaded."""
        self.fetch_new_messages.start()
        log.info("Episodic Memory Service loaded and task started.")

    async def cog_unload(self) -> None:
        """Cancels the background task when the cog is unloaded."""
        self.fetch_new_messages.cancel()
        log.info("Episodic Memory Service unloaded and task cancelled.")

    @tasks.loop(seconds=10.0)
    async def fetch_new_messages(self):
        """
        The main ETL loop (Stage 1). Periodically fetches pending message IDs
        from storage, retrieves the full message objects from Discord,
        and stores them back in storage.
        """
        if self.is_processing:
            log.debug("Previous fetch cycle still running. Skipping.")
            return

        self.is_processing = True
        try:
            pending_batch = await self.storage.get_pending_messages(limit=100)
            if not pending_batch:
                return

            log.info(f"Fetched {len(pending_batch)} pending messages for processing.")
            await self._fetch_and_store_messages(pending_batch)

        except Exception as e:
            log.error(f"An unexpected error occurred in the fetch_new_messages loop: {e}", exc_info=True)
            await func.report_error(e, "fetch_new_messages_loop")
        finally:
            self.is_processing = False

    async def _fetch_and_store_messages(self, pending_batch: list):
        """
        Fetches full discord.Message objects for a batch of pending messages
        and stores them in storage.

        Args:
            pending_batch: A list of tuples/dicts containing message metadata
                           (message_id, channel_id, guild_id).
        """
        messages_by_channel: dict[int, list[int]] = defaultdict(list)
        log.debug("Pending batch type: %s, sample: %s", type(pending_batch).__name__, pending_batch[:5])
        for row in pending_batch:
            # support dict rows returned by SQLiteStorage and sequence tuples/lists from other storages
            if isinstance(row, dict):
                message_id = row["message_id"]
                channel_id = row["channel_id"]
            else:
                try:
                    message_id, channel_id, *_ = row
                except Exception:
                    log.warning("Unexpected pending_batch item format: %r", row)
                    continue
            messages_by_channel[channel_id].append(message_id)

        fetched_messages: list[discord.Message] = []
        processed_ids: list[int] = []

        for channel_id, message_ids in messages_by_channel.items():
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                log.warning(f"Could not find channel {channel_id} or it's not a text channel. Marking messages as processed.")
                processed_ids.extend(message_ids)
                continue

            for message_id in message_ids:
                try:
                    message = await channel.fetch_message(message_id)
                    fetched_messages.append(message)
                except discord.NotFound:
                    log.warning(f"Message {message_id} not found in channel {channel_id}. It might have been deleted.")
                except discord.Forbidden:
                    log.error(f"Missing permissions to fetch message {message_id} in channel {channel_id}.")
                except Exception as e:
                    log.error(f"Failed to fetch message {message_id} due to an unexpected error: {e}", exc_info=True)
                    await func.report_error(e, f"fetch_message_{message_id}")
                finally:
                    # Mark as processed regardless of success or failure to avoid retrying forever.
                    processed_ids.append(message_id)

        if fetched_messages:
            await self.storage.store_messages_batch(fetched_messages)
            log.info(f"Successfully stored {len(fetched_messages)} messages in storage.")

        if processed_ids:
            await self.storage.mark_pending_messages_processed(processed_ids)
            log.info(f"Marked {len(processed_ids)} pending messages as processed.")

    @fetch_new_messages.before_loop
    async def before_fetch_loop(self):
        """Ensures the bot is ready before the loop starts."""
        await self.bot.wait_until_ready()
        log.info("Bot is ready. Episodic Memory Service fetch loop will now start.")


async def setup(bot: commands.Bot):
    """The setup function for the cog."""
    # Attempt to provide bot.db_manager as storage for backward compatibility.
    storage = getattr(bot, "db_manager", None)
    await bot.add_cog(EpisodicMemoryService(bot, storage))