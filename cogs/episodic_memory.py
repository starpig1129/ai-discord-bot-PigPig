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
        """Load the episodic memory service."""
        log.info("Episodic Memory Service loaded.")

    async def cog_unload(self) -> None:
        """Unload the episodic memory service."""
        log.info("Episodic Memory Service unloaded.")

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

            # Call MessageTracker's _process_channel_memory method directly
            try:
                # Initialize channel memory state if it doesn't exist
                state = await self.storage.get_channel_memory_state(channel.id)
                if state is None:
                    # Get the most recent message to initialize state
                    recent_messages = [msg async for msg in channel.history(limit=1)]
                    if recent_messages:
                        await self.storage.update_channel_memory_state(
                            channel_id=channel.id,
                            message_count=0,
                            start_message_id=recent_messages[0].id
                        )
                
                # Trigger memory processing through MessageTracker
                await self.message_tracker._process_channel_memory(channel)
                
                success_text = (
                    lang_manager.translate(guild_id, "commands", "memory", "force_update", "success")
                    if lang_manager
                    else "已成功觸發頻道記憶更新。"
                )
                await interaction.edit_original_response(content=success_text)
                
            except Exception as e:
                await func.report_error(e, "force_update_memory_processing")
                error_text = (
                    lang_manager.translate(guild_id, "commands", "memory", "force_update", "error")
                    if lang_manager
                    else "強制更新記憶失敗，已記錄錯誤。"
                )
                await interaction.edit_original_response(content=error_text)

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


async def setup(bot: commands.Bot):
    """The setup function for the cog."""
    # Deterministically require bot.episodic_storage; do not fall back to db_manager.
    storage = getattr(bot, "episodic_storage", None)
    if storage is None:
        log.error("bot.episodic_storage is missing when loading EpisodicMemoryService.")
        await func.report_error(RuntimeError("EpisodicStorage missing"), "episodic_memory_service_setup")
        raise RuntimeError("EpisodicStorage missing. Ensure bot.episodic_storage is initialized before loading this cog.")
    await bot.add_cog(EpisodicMemoryService(bot, storage))