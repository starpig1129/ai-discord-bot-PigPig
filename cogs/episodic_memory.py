# cogs/memory/services/episodic_memory_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Optional, List, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from addons.tokens import tokens
from function import func
from addons.settings import memory_config, MemoryConfig
from cogs.memory.interfaces.storage_interface import StorageInterface
from cogs.memory.interfaces.vector_store_interface import MemoryFragment
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

    def _translate_text(self, lang_manager: Any, guild_id: str, *args: str, **kwargs: Any) -> str:
        """Helper method to safely translate text with fallback."""
        try:
            if lang_manager and hasattr(lang_manager, 'translate'):
                return lang_manager.translate(guild_id, *args, **kwargs)
        except Exception as e:
            log.warning(f"Translation failed: {e}")
        
        # Fallback translations for memory commands
        arg_tuple = tuple(args)
        fallbacks: dict[tuple[str, ...], str] = {
            ("commands", "memory", "force_update", "starting"): "正在強制更新此頻道的記憶...",
            ("commands", "memory", "force_update", "not_text_channel"): "此指令必須在文字頻道中使用。",
            ("commands", "memory", "force_update", "success"): "已成功觸發頻道記憶更新。",
            ("commands", "memory", "force_update", "error"): "強制更新記憶失敗，已記錄錯誤。",
            ("commands", "memory", "search", "searching"): "正在搜尋情境記憶...",
            ("commands", "memory", "search", "no_parameters"): "請至少提供一個搜尋參數（vector_query、keyword_query、user_id 或 channel_id）。",
            ("commands", "memory", "search", "results_found"): "找到 {len} 筆相關記憶：\n\n",
            ("commands", "memory", "search", "no_results"): "找不到符合條件的記憶。",
            ("commands", "memory", "search", "not_implemented"): "搜尋功能尚未在儲存後端實現。請聯繫開發者。",
            ("commands", "memory", "search", "error"): "搜尋記憶時發生錯誤，已記錄錯誤日誌。"
        }
        
        return fallbacks.get(arg_tuple, args[-1] if args else "Translation not found")

    @app_commands.check(lambda interaction: interaction.user.id == tokens.bot_owner_id)
    @app_commands.command(name="force_update_memory", description="Force update this channel's episodic memory.")
    async def force_update_memory(self, interaction: discord.Interaction):
        """Force update the memory for the current channel. Owner only."""
        try:
            # localization via LanguageManager if available
            lang_manager = self.bot.get_cog("LanguageManager")
            guild_id = str(interaction.guild.id) if interaction.guild else "0"
            starting_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "force_update", "starting")

            # send initial ephemeral response
            await interaction.response.send_message(starting_text, ephemeral=True)

            channel = interaction.channel
            if not channel or not isinstance(channel, discord.TextChannel):
                not_channel_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "force_update", "not_text_channel")
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
                
                success_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "force_update", "success")
                await interaction.edit_original_response(content=success_text)
                
            except Exception as e:
                await func.report_error(e, "force_update_memory_processing")
                error_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "force_update", "error")
                await interaction.edit_original_response(content=error_text)

        except Exception as e:
            log.error("Error in force_update_memory: %s", e, exc_info=True)
            await func.report_error(e, "force_update_memory_command")
            # attempt to inform the user
            try:
                lang_manager = self.bot.get_cog("LanguageManager")
                guild_id = str(interaction.guild.id) if interaction.guild else "0"
                error_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "force_update", "error")
                # If original response exists, edit it; otherwise send a followup
                try:
                    await interaction.edit_original_response(content=error_text)
                except Exception:
                    await interaction.followup.send(error_text, ephemeral=True)
            except Exception:
                # swallow secondary errors to avoid crashing the command
                pass

    @app_commands.check(lambda interaction: interaction.user.id == tokens.bot_owner_id)
    @app_commands.command(name="search_episodic_memory", description="Search episodic memory with vector and keyword queries.")
    async def search_episodic_memory(
        self,
        interaction: discord.Interaction,
        vector_query: Optional[str] = None,
        keyword_query: Optional[str] = None,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None
    ):
        """Search episodic memory with multiple query parameters. Owner only."""
        try:
            # localization via LanguageManager if available
            lang_manager = self.bot.get_cog("LanguageManager")
            guild_id = str(interaction.guild.id) if interaction.guild else "0"
            
            searching_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "search", "searching")
            
            # send initial response
            await interaction.response.send_message(searching_text, ephemeral=True)
            
            # Validate that at least one search parameter is provided
            if not any([vector_query, keyword_query, user_id, channel_id]):
                no_params_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "search", "no_parameters")
                await interaction.edit_original_response(content=no_params_text)
                return
            
            try:
                search_results: List[MemoryFragment] = []
                
                # Try multiple search approaches in order of preference
                search_performed = False
                
                # 1. Check if bot has vector_manager with search capabilities
                vector_manager = getattr(self.bot, 'vector_manager', None)
                if vector_manager:
                    try:
                        vector_store = vector_manager.store  # type: ignore[attr-defined]
                        if hasattr(vector_store, 'search'):
                            search_results = await vector_store.search(
                                vector_query=vector_query,
                                keyword_query=keyword_query,
                                user_id=user_id,
                                channel_id=channel_id
                            )
                            search_performed = True
                    except Exception as e:
                        log.warning(f"Vector search failed: {e}")
                        search_results = []
                # 2. Fallback to direct storage method
                elif hasattr(self.storage, 'search_episodic_memory'):
                    search_results = await self.storage.search_episodic_memory(  # type: ignore[attr-defined]
                        vector_query=vector_query,
                        keyword_query=keyword_query,
                        user_id=user_id,
                        channel_id=channel_id
                    )
                    search_performed = True
                # 3. Try individual vector and keyword search methods using bot's vector_manager
                elif vector_manager:
                    try:
                        vector_store = vector_manager.store  # type: ignore[attr-defined]
                        results = []
                        
                        if vector_query and hasattr(vector_store, 'search_memories_by_vector'):
                            vector_results = await vector_store.search_memories_by_vector(
                                query_text=vector_query,
                                user_id=user_id,
                                channel_id=channel_id
                            )
                            results.extend(vector_results)
                        
                        if keyword_query and hasattr(vector_store, 'search_memories_by_keyword'):
                            keyword_results = await vector_store.search_memories_by_keyword(
                                query_text=keyword_query,
                                user_id=user_id,
                                channel_id=channel_id
                            )
                            results.extend(keyword_results)
                        
                        # Remove duplicates based on fragment_id
                        seen_ids = set()
                        unique_results = []
                        for result in results:
                            fragment_id = result.metadata.get('fragment_id')
                            if fragment_id not in seen_ids:
                                seen_ids.add(fragment_id)
                                unique_results.append(result)
                        
                        search_results = unique_results
                        search_performed = True
                    except Exception as e:
                        log.warning(f"Individual vector search failed: {e}")
                        search_results = []
                
                if not search_performed:
                    # Handle case where storage doesn't have search method yet
                    not_implemented_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "search", "not_implemented")
                    await interaction.edit_original_response(content=not_implemented_text)
                    return
                
                # Format and return results
                if search_results:
                    # Format results with proper parameter substitution
                    base_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "search", "results_found")
                    try:
                        # Try to format with len parameter if template supports it
                        results_text = base_text.format(len=len(search_results))
                    except (KeyError, ValueError):
                        # Fallback to manual formatting if translation template doesn't support formatting
                        results_text = f"找到 {len(search_results)} 筆相關記憶：\n\n"
                    
                    # Format each result
                    formatted_results = []
                    for i, result in enumerate(search_results[:10], 1):
                        formatted_result = f"**結果 {i}:**\n"
                        formatted_result += f"內容：{result.content}\n"
                        if result.score is not None:
                            formatted_result += f"相似度：{result.score:.3f}\n"
                        if result.metadata.get('timestamp'):
                            from datetime import datetime
                            timestamp = datetime.fromtimestamp(result.metadata['timestamp'])
                            formatted_result += f"時間：{timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        formatted_results.append(formatted_result)
                    
                    results_text += "\n\n".join(formatted_results)
                    
                    if len(search_results) > 10:
                        results_text += f"\n\n... 及其他 {len(search_results) - 10} 筆結果"
                else:
                    results_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "search", "no_results")
                
                await interaction.edit_original_response(content=results_text)
                
            except Exception as e:
                await func.report_error(e, "episodic_memory_search")
                error_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "search", "error")
                await interaction.edit_original_response(content=error_text)
                
        except Exception as e:
            log.error("Error in search_episodic_memory: %s", e, exc_info=True)
            await func.report_error(e, "search_episodic_memory_command")
            
            # attempt to inform the user
            try:
                lang_manager = self.bot.get_cog("LanguageManager")
                guild_id = str(interaction.guild.id) if interaction.guild else "0"
                error_text = self._translate_text(lang_manager, guild_id, "commands", "memory", "search", "error")
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