import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional

from .story.manager import StoryManager
from .story.ui import UIManager
from .system_prompt.manager import SystemPromptManager


class StoryManagerCog(commands.Cog, name="StoryManagerCog"):
    """
    故事模組主要 Cog
    
    重構後的故事模組採用 UI 驅動設計：
    - 單一 /story 命令作為入口點
    - 所有功能透過 Discord UI 元件操作
    - 臨時性介面降低狀態管理複雜度
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.story_manager: Optional[StoryManager] = None
        self.ui_manager: Optional[UIManager] = None
        self.logger.info("StoryManagerCog (UI版本) 已初始化")

    async def cog_load(self):
        """
        非同步初始化 Cog 及其管理器。
        """
        system_prompt_manager_cog = self.bot.get_cog("SystemPromptManagerCog")
        if not system_prompt_manager_cog:
            self.logger.error("無法找到 SystemPromptManagerCog，StoryManagerCog 將無法正常運作。")
            return
        
        system_prompt_manager = system_prompt_manager_cog.manager
        
        self.story_manager = StoryManager(self.bot, self, system_prompt_manager)
        self.ui_manager = UIManager(self.bot, self.story_manager, system_prompt_manager)
        
        await self.story_manager.initialize()
        self.logger.info("StoryManagerCog has been loaded and initialized.")

    story = app_commands.Group(name="story", description="與故事模式相關的指令")

    @story.command(name="menu", description="🎭 開啟故事管理選單")
    async def story_menu(self, interaction: discord.Interaction):
        """
        故事管理主命令
        
        根據當前頻道狀態顯示對應的 UI 介面：
        - 無故事：顯示初始設定選單（創建世界、角色、開始故事）
        - 有故事：顯示故事控制面板（加入、暫停、結束等）
        """
        try:
            await self.ui_manager.show_main_menu(interaction)
            
        except Exception as e:
            self.logger.error(f"故事選單錯誤: {e}", exc_info=True)
            error_message = "❌ 載入故事選單時發生錯誤，請稍後再試。"
            
            if interaction.response.is_done():
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.response.send_message(error_message, ephemeral=True)

    @story.command(name="intervene", description="🎬 對故事走向進行干預")
    async def intervene(self, interaction: discord.Interaction):
        """
        Allows a user to intervene in the story with OOC instructions for the director.
        """
        try:
            # Check if a story is active in this channel
            db = self.story_manager._get_db(interaction.guild_id)
            story_instance = db.get_story_instance(interaction.channel_id)

            if not story_instance or not story_instance.is_active:
                await interaction.response.send_message(
                    "❌ 此頻道目前沒有正在進行的故事。無法進行干預。",
                    ephemeral=True
                )
                return

            # Show the intervention modal
            from .story.ui.modals import InterventionModal
            modal = InterventionModal(self.story_manager)
            await interaction.response.send_modal(modal)

        except Exception as e:
            self.logger.error(f"Error in /story intervene command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ 執行干預指令時發生錯誤。",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_ready(self):
        """Cog 準備就緒事件"""
        self.logger.info("故事模組已準備就緒")

    async def handle_story_message(self, message: discord.Message):
        """
        處理故事頻道中的訊息
        
        此方法由 bot.py 的 on_message 事件呼叫，
        當頻道模式為 'story' 時處理使用者的故事互動。
        
        Args:
            message: Discord 訊息物件
        """
        if not self.story_manager:
            self.logger.warning("StoryManager 未初始化，跳過訊息處理")
            return
        
        try:
            await self.story_manager.process_story_message(message)
            
        except Exception as e:
            self.logger.error(
                f"處理故事訊息時發生錯誤 (頻道 {message.channel.id}): {e}", 
                exc_info=True
            )
            
            # 發送友善的錯誤訊息
            error_embed = discord.Embed(
                title="🎭 故事暫時中斷",
                description="故事之神似乎打了個盹，請稍後再試...",
                color=discord.Color.orange()
            )
            error_embed.set_footer(text=f"錯誤詳情: {str(e)[:100]}")
            
            try:
                await message.reply(embed=error_embed)
            except:
                # 如果無法回覆，嘗試發送到頻道
                try:
                    await message.channel.send(embed=error_embed)
                except:
                    # 最後的備用方案
                    await message.channel.send("❌ 故事處理時發生錯誤，請稍後再試。")


async def setup(bot: commands.Bot):
    """
    設定函式，將 Cog 加入到 bot 中
    
    Args:
        bot: Discord Bot 實例
    """
    await bot.add_cog(StoryManagerCog(bot))