# cogs/memory/services/episodic_memory_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from addons.tokens import tokens
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

    @app_commands.check(lambda interaction: interaction.user.id == tokens.bot_owner_id)
    @app_commands.command(name="force_update_memory", description="Force update this channel's episodic memory.")
    async def force_update_memory(self, interaction: discord.Interaction):
        """Force update the memory for the current channel. Owner only."""
        try:
            # localization via LanguageManager if available
            lang_manager = self.bot.get_cog("LanguageManager")
            guild_id = str(interaction.guild.id) if interaction.guild else "0"
            starting_text = (
                lang_manager.translate(guild_id, "commands", "memory", "force_update", "starting")
                if lang_manager
                else "正在強制更新此頻道的記憶..."
            )

            # send initial ephemeral response
            await interaction.response.send_message(starting_text, ephemeral=True)

            channel = interaction.channel
            if not channel or not isinstance(channel, discord.TextChannel):
                not_channel_text = (
                    lang_manager.translate(guild_id, "commands", "memory", "force_update", "not_text_channel")
                    if lang_manager
                    else "此指令必須在文字頻道中使用。"
                )
                await interaction.edit_original_response(content=not_channel_text)
                return

            # explicit limit to avoid unlimited fetches
            limit = 200
            messages = [msg async for msg in channel.history(limit=limit)]
            if not messages:
                no_messages_text = (
                    lang_manager.translate(guild_id, "commands", "memory", "force_update", "no_messages")
                    if lang_manager
                    else "未找到可更新的訊息。"
                )
                await interaction.edit_original_response(content=no_messages_text)
                return

            # store messages batch
            await self.storage.store_messages_batch(messages)

            success_text = (
                lang_manager.translate(guild_id, "commands", "memory", "force_update", "success", count=len(messages))
                if lang_manager
                else f"已更新 {len(messages)} 條訊息的記憶。"
            )
            await interaction.edit_original_response(content=success_text)

        except Exception as e:
            log.error("Error in force_update_memory: %s", e, exc_info=True)
            await func.report_error(e, "force_update_memory_command")
            # attempt to inform the user
            try:
                lang_manager = self.bot.get_cog("LanguageManager")
                guild_id = str(interaction.guild.id) if interaction.guild else "0"
                error_text = (
                    lang_manager.translate(guild_id, "commands", "memory", "force_update", "error")
                    if lang_manager
                    else "強制更新記憶失敗，已記錄錯誤。"
                )
                # If original response exists, edit it; otherwise send a followup
                try:
                    await interaction.edit_original_response(content=error_text)
                except Exception:
                    await interaction.followup.send(error_text, ephemeral=True)
            except Exception:
                # swallow secondary errors to avoid crashing the command
                pass

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