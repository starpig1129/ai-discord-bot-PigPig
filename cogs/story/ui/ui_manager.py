import discord
from discord.ext import commands
import logging
from typing import Optional

from ..manager import StoryManager
from .views import InitialStoryView, ActiveStoryView


class UIManager:
    """
    故事模組的 UI 管理器
    
    負責協調和管理所有 UI 介面的顯示、更新與生命週期。
    採用臨時性 (ephemeral) 介面設計，降低狀態管理複雜度。
    """
    
    def __init__(self, bot: commands.Bot, story_manager: StoryManager):
        self.bot = bot
        self.story_manager = story_manager
        self.logger = logging.getLogger(__name__)
        
    async def show_main_menu(self, interaction: discord.Interaction):
        """
        顯示主要的故事管理選單
        
        根據當前頻道是否有活躍的故事實例，決定顯示：
        1. InitialStoryView - 故事開始前的準備介面
        2. ActiveStoryView - 正在進行故事的管理介面
        
        Args:
            interaction: Discord 互動物件
        """
        try:
            # 檢查頻道權限
            channel_manager = self.bot.get_cog('ChannelManager')
            if not channel_manager:
                await interaction.response.send_message(
                    "❌ 系統錯誤：無法找到頻道管理器", 
                    ephemeral=True
                )
                return
            
            # 檢查當前頻道是否有活躍的故事實例
            db = self.story_manager._get_db(interaction.guild_id)
            self.logger.info(f"[DEBUG] show_main_menu 調用 db.initialize() - Guild: {interaction.guild_id}")
            db.initialize()
            
            story_instance = db.get_story_instance(interaction.channel_id)
            has_active_story = story_instance and story_instance.is_active
            
            if has_active_story:
                # 顯示正在進行故事的管理介面
                view = ActiveStoryView(self.story_manager, story_instance)
                embed = self._create_active_story_embed(story_instance)
                await interaction.response.send_message(
                    embed=embed, 
                    view=view, 
                    ephemeral=True
                )
            else:
                # 顯示故事開始前的準備介面
                view = InitialStoryView(self.story_manager, interaction.channel_id, interaction.guild_id)
                
                # 動態載入世界選單選項
                await self._update_world_select_options(view, interaction.guild_id)
                
                embed = await self._create_initial_story_embed(interaction.guild_id, interaction.channel_id)
                await interaction.response.send_message(
                    embed=embed,
                    view=view,
                    ephemeral=True
                )
                
        except Exception as e:
            self.logger.error(f"顯示主選單時發生錯誤: {e}", exc_info=True)
            error_message = "❌ 載入故事選單時發生錯誤，請稍後再試。"
            
            if interaction.response.is_done():
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.response.send_message(error_message, ephemeral=True)
    
    async def _create_initial_story_embed(self, guild_id: int, channel_id: int) -> discord.Embed:
        """創建初始故事選單的 Embed"""
        embed = discord.Embed(
            title="🎭 故事管理選單",
            description="歡迎來到故事世界！選擇以下操作來開始你的冒險：",
            color=discord.Color.blue()
        )
        
        # 檢查是否有可用的世界
        db = self.story_manager._get_db(guild_id)
        worlds = db.get_all_worlds()
        
        if worlds:
            world_list = "\n".join([f"• **{world.world_name}**" for world in worlds[:5]])
            if len(worlds) > 5:
                world_list += f"\n... 以及其他 {len(worlds) - 5} 個世界"
            embed.add_field(
                name="🌍 可用世界",
                value=world_list,
                inline=False
            )
        else:
            embed.add_field(
                name="🌍 可用世界",
                value="目前沒有可用的世界，請先創建一個！",
                inline=False
            )
        
        embed.set_footer(text="💡 使用下方按鈕來管理世界、角色或開始故事")
        return embed
    
    def _create_active_story_embed(self, story_instance) -> discord.Embed:
        """創建進行中故事的 Embed"""
        embed = discord.Embed(
            title="🎮 故事控制面板",
            description=f"正在進行的故事：**{story_instance.world_name}**",
            color=discord.Color.green()
        )
        
        # 顯示故事狀態
        status_text = "✅ 進行中" if story_instance.is_active else "⏸️ 已暫停"
        embed.add_field(name="📊 狀態", value=status_text, inline=True)
        
        # 顯示參與角色數量
        char_count = len(story_instance.active_characters)
        embed.add_field(name="👥 參與角色", value=f"{char_count} 位", inline=True)
        
        # 顯示最近事件
        if story_instance.event_log:
            recent_event = story_instance.event_log[-1]
            if len(recent_event) > 100:
                recent_event = recent_event[:100] + "..."
            embed.add_field(name="📜 最近事件", value=recent_event, inline=False)
        
        embed.set_footer(text="💡 使用下方按鈕來管理正在進行的故事")
        return embed
    
    async def _update_world_select_options(self, view, guild_id: int):
        """更新視圖中的世界選擇選單選項"""
        try:
            db = self.story_manager._get_db(guild_id)
            self.logger.info(f"[DEBUG] _update_world_select_options 調用 db.initialize() - Guild: {guild_id}")
            db.initialize()
            worlds = db.get_all_worlds()
            
            # 找到世界選擇組件並更新選項
            for item in view.children:
                if isinstance(item, discord.ui.Select):
                    options = []
                    if worlds:
                        for world in worlds[:25]:  # Discord 限制最多 25 個選項
                            options.append(discord.SelectOption(
                                label=world.world_name,
                                value=world.world_name,
                                description=world.background[:100] if world.background else "無描述"
                            ))
                    else:
                        options.append(discord.SelectOption(
                            label="無可用世界",
                            value="none",
                            description="請先創建一個世界"
                        ))
                    
                    item.options = options
                    break
                    
        except Exception as e:
            self.logger.error(f"更新世界選單選項錯誤: {e}", exc_info=True)