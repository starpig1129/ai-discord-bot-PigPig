from __future__ import annotations
import discord
from discord.ext import commands
import logging
from typing import List, Optional, TYPE_CHECKING

from ..manager import StoryManager
from ..models import StoryInstance, StoryWorld
from .modals import WorldCreateModal, CharacterCreateModal

if TYPE_CHECKING:
    from .ui_manager import UIManager


class InitialStoryView(discord.ui.View):
    """
    初始故事視圖
    
    用於故事開始前的準備工作，包含：
    - 世界選擇選單
    - 創建世界按鈕
    - 創建角色按鈕
    - 開始故事按鈕
    """
    
    def __init__(self, story_manager: StoryManager, channel_id: int, guild_id: int, ui_manager: UIManager):
        super().__init__(timeout=300)  # 5分鐘超時
        self.story_manager = story_manager
        self.ui_manager = ui_manager
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.selected_world: Optional[str] = None
        self.logger = logging.getLogger(__name__)
        
    async def on_timeout(self):
        """視圖超時處理"""
        # 禁用所有組件
        for item in self.children:
            item.disabled = True
    
    @discord.ui.select(
        placeholder="🌍 選擇一個世界來開始故事...",
        options=[discord.SelectOption(label="載入中...", value="loading")]
    )
    async def world_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """世界選擇選單"""
        try:
            if select.values[0] == "loading":
                await interaction.response.send_message("⏳ 正在載入世界列表...", ephemeral=True)
                return
                
            self.selected_world = select.values[0]
            
            # 更新開始故事按鈕狀態
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.custom_id == "start_story":
                    item.disabled = False
                    break
            
            # 載入所選世界的資訊
            db = self.story_manager._get_db(self.guild_id)
            world = db.get_world(self.selected_world)
            
            embed = discord.Embed(
                title=f"🌍 已選擇世界：{self.selected_world}",
                description=world.background[:500] + ("..." if len(world.background) > 500 else ""),
                color=discord.Color.blue()
            )
            
            await interaction.response.edit_message(embed=embed, view=self)
            
        except Exception as e:
            self.logger.error(f"世界選擇錯誤: {e}", exc_info=True)
            await interaction.response.send_message("❌ 載入世界資訊時發生錯誤", ephemeral=True)
    
    @discord.ui.button(label="🌍 創建新世界", style=discord.ButtonStyle.primary, row=0)
    async def create_world_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """創建世界按鈕"""
        try:
            modal = WorldCreateModal(self.story_manager, self.guild_id)
            await interaction.response.send_modal(modal)
            
            # 等待 Modal 完成後重新載入世界列表
            await modal.wait()
            await self._refresh_world_select()
            
        except Exception as e:
            self.logger.error(f"創建世界按鈕錯誤: {e}", exc_info=True)
    
    @discord.ui.button(label="👤 創建角色", style=discord.ButtonStyle.secondary, row=1)
    async def create_character_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """創建角色按鈕"""
        try:
            world_name = self.selected_world if self.selected_world else None
            modal = CharacterCreateModal(self.story_manager, self.guild_id, world_name)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            self.logger.error(f"創建角色按鈕錯誤: {e}", exc_info=True)

    @discord.ui.button(label="📥 從預設載入角色", style=discord.ButtonStyle.secondary, row=1)
    async def load_default_character_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """從預設載入角色按鈕"""
        try:
            await self.ui_manager.handle_load_default_character(interaction)
        except Exception as e:
            self.logger.error(f"載入預設角色按鈕錯誤: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 載入預設角色時發生錯誤", ephemeral=True)
    
    @discord.ui.button(
        label="🎬 開始故事", 
        style=discord.ButtonStyle.success, 
        disabled=True,
        custom_id="start_story"
    )
    async def start_story_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """開始故事按鈕"""
        try:
            if not self.selected_world:
                await interaction.response.send_message(
                    "❌ 請先選擇一個世界",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # 檢查頻道模式
            channel_manager = interaction.client.get_cog('ChannelManager')
            if not channel_manager:
                await interaction.followup.send("❌ 系統錯誤：無法找到頻道管理器", ephemeral=True)
                return
            
            is_allowed, _, channel_mode = channel_manager.is_allowed_channel(
                interaction.channel, 
                str(interaction.guild_id)
            )
            
            if not is_allowed or channel_mode != 'story':
                await interaction.followup.send(
                    "❌ 請先由管理員使用 `/set_channel_mode` 將此頻道設定為 **故事模式**",
                    ephemeral=True
                )
                return
            
            # 檢查是否已有故事在進行
            db = self.story_manager._get_db(self.guild_id)
            existing_instance = db.get_story_instance(self.channel_id)
            if existing_instance and existing_instance.is_active:
                await interaction.followup.send(
                    "❌ 這個頻道已經有一個正在進行的故事了！",
                    ephemeral=True
                )
                return
            
            # 創建新的故事實例
            from ..models import StoryInstance
            new_instance = StoryInstance(
                channel_id=self.channel_id,
                guild_id=self.guild_id,
                world_name=self.selected_world
            )
            
            # 初始化預設狀態
            new_instance = self.story_manager.state_manager.initialize_default_state(new_instance)
            db.save_story_instance(new_instance)

            # 載入世界資訊
            world = db.get_world(self.selected_world)
            
            # 發送成功訊息到頻道（公開）
            embed = discord.Embed(
                title="🎬 故事開始！",
                description=f"**{self.selected_world}** 的冒險篇章已在此頻道開啟！",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="🌍 世界背景",
                value=world.background[:800] + ("..." if len(world.background) > 800 else ""),
                inline=False
            )
            embed.set_footer(text="💡 在此頻道輸入訊息來與故事互動")
            
            # 發送到頻道
            await interaction.channel.send(embed=embed)
            
            # 私人確認訊息
            await interaction.followup.send(
                f"✅ 故事已成功在此頻道開始！\n🌍 世界：**{self.selected_world}**",
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"開始故事錯誤: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ 開始故事時發生錯誤，請稍後再試",
                ephemeral=True
            )
    
    async def _refresh_world_select(self):
        """重新整理世界選擇選單"""
        try:
            db = self.story_manager._get_db(self.guild_id)
            worlds = db.get_all_worlds()
            
            # 更新選項
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
            
            # 找到世界選擇組件並更新
            for item in self.children:
                if isinstance(item, discord.ui.Select):
                    item.options = options
                    break
                    
        except Exception as e:
            self.logger.error(f"重新整理世界選單錯誤: {e}", exc_info=True)


class ActiveStoryView(discord.ui.View):
    """
    進行中故事視圖
    
    用於管理正在進行的故事，包含：
    - 加入故事按鈕
    - 暫停/恢復故事按鈕（管理員）
    - 結束故事按鈕（管理員）
    """
    
    def __init__(self, story_manager: StoryManager, story_instance: StoryInstance):
        super().__init__(timeout=300)
        self.story_manager = story_manager
        self.story_instance = story_instance
        self.logger = logging.getLogger(__name__)
        
        # 根據故事狀態設定暫停/恢復按鈕的初始狀態
        self._update_pause_button_state()
    
    def _update_pause_button_state(self):
        """更新暫停/恢復按鈕的狀態"""
        for item in self.children:
            if isinstance(item, discord.ui.Button) and hasattr(item.callback, '__name__') and item.callback.__name__ == 'pause_story_button':
                if self.story_instance.is_active:
                    item.label = "⏸️ 暫停故事"
                    item.style = discord.ButtonStyle.secondary
                else:
                    item.label = "▶️ 恢復故事"
                    item.style = discord.ButtonStyle.success
                break
    
    @discord.ui.button(label="🎭 加入故事", style=discord.ButtonStyle.primary)
    async def join_story_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """加入故事按鈕"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            db = self.story_manager._get_db(interaction.guild_id)
            
            # 尋找使用者在此世界的角色
            user_characters = db.get_characters_by_user(
                interaction.user.id,
                self.story_instance.world_name
            )
            
            if not user_characters:
                await interaction.followup.send(
                    f"❌ 你在 **{self.story_instance.world_name}** 世界中還沒有創建任何角色。\n"
                    f"請先使用 `/story` 創建角色。",
                    ephemeral=True
                )
                return
            
            # 使用第一個角色（未來可以改為讓使用者選擇）
            character_to_join = user_characters[0]
            
            if character_to_join.character_id in self.story_instance.active_characters:
                await interaction.followup.send(
                    f"✅ 你的角色 **{character_to_join.name}** 已經在故事中了！",
                    ephemeral=True
                )
                return
            
            # 將角色加入故事
            self.story_instance.active_characters.append(character_to_join.character_id)
            db.save_story_instance(self.story_instance)
            
            # 發送成功訊息到頻道
            embed = discord.Embed(
                title="🎭 新角色加入！",
                description=f"**{character_to_join.name}** 加入了冒險！",
                color=discord.Color.green()
            )
            embed.add_field(
                name="👤 角色名稱",
                value=character_to_join.name,
                inline=True
            )
            embed.add_field(
                name="🎮 操控者",
                value=interaction.user.mention,
                inline=True
            )
            embed.add_field(
                name="📝 角色描述",
                value=character_to_join.description[:300] + ("..." if len(character_to_join.description) > 300 else ""),
                inline=False
            )
            
            await interaction.channel.send(embed=embed)
            
            await interaction.followup.send(
                f"✅ **{character_to_join.name}** 已成功加入故事！",
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"加入故事錯誤: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ 加入故事時發生錯誤，請稍後再試",
                ephemeral=True
            )
    
    @discord.ui.button(label="⏸️ 暫停故事", style=discord.ButtonStyle.secondary)
    async def pause_story_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """暫停故事按鈕（管理員專用）"""
        try:
            # 檢查管理員權限
            channel_manager = interaction.client.get_cog('ChannelManager')
            if not channel_manager or not await channel_manager.check_admin_permissions(interaction):
                return
            
            await interaction.response.defer(ephemeral=True)
            
            if self.story_instance.is_active:
                # 暫停故事
                self.story_instance.is_active = False
                button.label = "▶️ 恢復故事"
                button.style = discord.ButtonStyle.success
                message = "⏸️ 故事已暫停"
            else:
                # 恢復故事
                self.story_instance.is_active = True
                button.label = "⏸️ 暫停故事"
                button.style = discord.ButtonStyle.secondary
                message = "▶️ 故事已恢復"
            
            db = self.story_manager._get_db(interaction.guild_id)
            db.save_story_instance(self.story_instance)
            
            await interaction.edit_original_response(view=self)
            await interaction.channel.send(message)
            
        except Exception as e:
            self.logger.error(f"暫停故事錯誤: {e}", exc_info=True)
    
    @discord.ui.button(label="🔚 結束故事", style=discord.ButtonStyle.danger)
    async def end_story_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """結束故事按鈕（管理員專用）"""
        try:
            # 檢查管理員權限
            channel_manager = interaction.client.get_cog('ChannelManager')
            if not channel_manager or not await channel_manager.check_admin_permissions(interaction):
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # 結束故事
            self.story_instance.is_active = False
            db = self.story_manager._get_db(interaction.guild_id)
            db.save_story_instance(self.story_instance)
            
            # 禁用所有按鈕
            for item in self.children:
                item.disabled = True
            
            await interaction.edit_original_response(view=self)
            
            embed = discord.Embed(
                title="🔚 故事結束",
                description=f"**{self.story_instance.world_name}** 的冒險篇章已經落下帷幕。",
                color=discord.Color.red()
            )
            embed.set_footer(text="感謝所有參與者的精彩演出！")
            
            await interaction.channel.send(embed=embed)
            await interaction.followup.send("✅ 故事已結束", ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"結束故事錯誤: {e}", exc_info=True)