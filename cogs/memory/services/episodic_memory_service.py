# cogs/memory/services/episodic_memory_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Optional

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

    def __init__(self, bot: "PigPig | commands.Bot", storage: "StorageInterface"):
        """
        Args:
            bot (PigPig | commands.Bot): The bot instance.
            storage (StorageInterface): Storage backend implementing StorageInterface.
                                       If None, will fall back to bot.episodic_storage for compatibility.
        """
        # Keep runtime typing flexible to accept either the concrete PigPig bot or a generic commands.Bot
        self.bot = bot  # type: ignore[assignment]
        # Accept a StorageInterface; allow fallback to bot.episodic_storage for compatibility.
        self.storage: StorageInterface = storage
        self.settings: MemoryConfig = memory_config
        self.message_tracker: MessageTracker = bot.message_tracker  # type: ignore[assignment]
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
        # Track consecutive server-side failures per channel for diagnostics.
        channel_failures: dict[int, int] = defaultdict(int)

        for channel_id, message_ids in messages_by_channel.items():
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                log.warning(f"Could not find channel {channel_id} or it's not a text channel. Marking messages as processed.")
                processed_ids.extend(message_ids)
                continue

            for message_id in message_ids:
                # Implement retry with exponential backoff for transient server errors.
                max_retries = 3
                base_delay = 1.0
                for attempt in range(1, max_retries + 1):
                    try:
                        log.debug(
                            "Fetching message %s from channel %s (attempt %d/%d)",
                            message_id,
                            channel_id,
                            attempt,
                            max_retries,
                        )
                        message = await channel.fetch_message(message_id)
                        fetched_messages.append(message)
                        # Reset consecutive server failure counter on success.
                        channel_failures[channel_id] = 0
                        break
                    except discord.NotFound:
                        log.warning(
                            "Message %s not found in channel %s. It might have been deleted.",
                            message_id,
                            channel_id,
                        )
                        break
                    except discord.Forbidden:
                        log.error(
                            "Missing permissions to fetch message %s in channel %s.",
                            message_id,
                            channel_id,
                        )
                        break
                    except discord.errors.DiscordServerError as e:
                        # Server-side 5xx errors from Discord - retryable.
                        channel_failures[channel_id] += 1
                        log.warning(
                            "Server error fetching message %s in channel %s (attempt %d/%d): %s",
                            message_id,
                            channel_id,
                            attempt,
                            max_retries,
                            e,
                        )
                        if attempt == max_retries:
                            log.error(
                                "Max retries reached for message %s in channel %s. Reporting error.",
                                message_id,
                                channel_id,
                            )
                            await func.report_error(e, f"fetch_message_{message_id}")
                        else:
                            backoff = base_delay * (2 ** (attempt - 1))
                            log.debug(
                                "Backing off for %.1f seconds before retrying message %s",
                                backoff,
                                message_id,
                            )
                            await asyncio.sleep(backoff)
                            continue
                    except discord.HTTPException as e:
                        # Non-server HTTP exceptions (likely 4xx) - do not retry.
                        log.warning(
                            "HTTP error fetching message %s in channel %s: %s",
                            message_id,
                            channel_id,
                            e,
                        )
                        await func.report_error(e, f"fetch_message_{message_id}")
                        break
                    except Exception as e:
                        # Unexpected exceptions - report and stop retrying this message.
                        log.error(
                            "Failed to fetch message %s due to unexpected error: %s",
                            message_id,
                            e,
                            exc_info=True,
                        )
                        await func.report_error(e, f"fetch_message_{message_id}")
                        break
                # After attempts, mark as processed to avoid perpetual retries.
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

            # Trigger vectorization and retention strategy for the stored messages.
            vector_note = ""
            try:
                # import inside function to avoid circular imports
                from cogs.memory.services.vectorization_service import VectorizationService

                vector_manager = getattr(self.bot, "vector_manager", None)
                vector_service = VectorizationService(bot=self.bot, storage=self.storage, vector_manager=vector_manager, settings=self.settings)

                # Ensure we pass a clean list[int] to the vectorization service
                message_ids = [int(getattr(m, "id")) for m in messages if getattr(m, "id", None) is not None]
                await vector_service.process_unvectorized_messages(message_ids=message_ids)

                vector_note = (
                    lang_manager.translate(guild_id, "commands", "memory", "force_update", "post_vectorization", count=len(messages))
                    if lang_manager
                    else " 已完成儲存、向量化及歸檔/刪除作業。"
                )
            except Exception as e:
                await func.report_error(e, "force_update_memory_vectorization")
                vector_note = (
                    lang_manager.translate(guild_id, "commands", "memory", "force_update", "post_vectorization_error", count=len(messages))
                    if lang_manager
                    else " 儲存完成，但向量化或歸檔/刪除時發生錯誤，已記錄。"
                )

            success_text = (
                lang_manager.translate(guild_id, "commands", "memory", "force_update", "success", count=len(messages))
                if lang_manager
                else f"已更新 {len(messages)} 條訊息的記憶。"
            )
            await interaction.edit_original_response(content=success_text + vector_note)

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
    # Provide episodic_storage from bot when available; fall back to legacy db_manager if present.
    storage = getattr(bot, "episodic_storage", None) or getattr(bot, "db_manager", None)
    await bot.add_cog(EpisodicMemoryService(bot, storage))