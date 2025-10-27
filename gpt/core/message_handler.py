# -*- coding: utf-8 -*-
import discord
import asyncio
from typing import TYPE_CHECKING, Optional
from gpt.processing_cache import processing_cache
from gpt.performance_monitor import PerformanceMonitor
from function import func

if TYPE_CHECKING:
    from bot import PigPig
    from gpt.core.action_dispatcher import ActionDispatcher

class MessageHandler:
    """負責處理傳入的 Discord 訊息並協調回應生成。"""

    def __init__(self, bot: 'PigPig', action_dispatcher: 'ActionDispatcher', performance_monitor: 'PerformanceMonitor'):
        """
        初始化 MessageHandler。

        Args:
            bot: PigPig bot 的實例。
            action_dispatcher: 用於選擇和執行工具的 ActionDispatcher。
            performance_monitor: 用於追蹤性能的 PerformanceMonitor。
        """
        self.bot = bot
        self.action_dispatcher = action_dispatcher
        self.performance_monitor = performance_monitor

    async def handle_message(self, message: discord.Message):
        """
        處理單一 Discord 訊息。

        此方法包含從 bot.py 的 on_message 遷移而來的核心邏輯，
        負責處理頻道權限、故事模式以及標準的訊息回應流程。

        Args:
            message: 要處理的 discord.Message 物件。
        """
        self.performance_monitor.start_timer("total_response_time")
        try:
            guild_id = str(message.guild.id)
            prompt = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
            user_id = str(message.author.id)
            channel_id = str(message.channel.id)

            # 檢查快取
            cached_result = processing_cache.get_cached_result(prompt, user_id, channel_id)
            if cached_result:
                self.performance_monitor.increment_counter("cache_hits")
                await message.reply(cached_result)
                return
            else:
                self.performance_monitor.increment_counter("cache_misses")

            channel_manager = self.bot.get_cog('ChannelManager')
            if not channel_manager:
                return

            is_allowed, auto_response_enabled, channel_mode = channel_manager.is_allowed_channel(message.channel, guild_id)
            if not is_allowed:
                return

            if channel_mode == 'story':
                story_cog = self.bot.get_cog('StoryManagerCog')
                if story_cog:
                    asyncio.create_task(story_cog.handle_story_message(message))
                return

            if (self.bot.user.id in message.raw_mentions and not message.mention_everyone) or auto_response_enabled:
                if not self.action_dispatcher:
                    await message.reply("系統正在初始化，請稍後再試。")
                    return

                message_to_edit = await message.reply("思考中...")
                try:
                    self.performance_monitor.start_timer("tool_execution_time")
                    execute_action = await self.action_dispatcher.choose_act(prompt, message, message_to_edit)
                    self.performance_monitor.stop_timer("tool_execution_time")

                    self.performance_monitor.start_timer("llm_generation_time")
                    final_result = await execute_action(message_to_edit, prompt, message)
                    self.performance_monitor.stop_timer("llm_generation_time")
                    
                    if final_result:
                        processing_cache.cache_result(prompt, user_id, channel_id, final_result)
                except Exception as e:
                    await func.func.report_error(e, "Message handling failed")
                    await message_to_edit.edit(content=f"糟糕，處理你的訊息時發生了錯誤：{e}")
        finally:
            self.performance_monitor.stop_timer("total_response_time")