from __future__ import annotations
import discord
from discord.ext import commands
import logging
from typing import List, Optional, TYPE_CHECKING

from ..manager import StoryManager
from ..models import StoryInstance, StoryWorld, StoryCharacter
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
                description=world.attributes.get('description', '無描述')[:500] + ("..." if len(world.attributes.get('description', '')) > 500 else ""),
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
            # 角色創建不再與特定世界綁定
            modal = CharacterCreateModal(self.story_manager, self.guild_id)
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

            # 檢查頻道模式
            channel_manager = interaction.client.get_cog('ChannelManager')
            if not channel_manager:
                await interaction.response.send_message("❌ 系統錯誤：無法找到頻道管理器", ephemeral=True)
                return
            
            is_allowed, _, channel_mode = channel_manager.is_allowed_channel(
                interaction.channel,
                str(interaction.guild_id)
            )
            
            if not is_allowed or channel_mode != 'story':
                await interaction.response.send_message(
                    "❌ 請先由管理員使用 `/set_channel_mode` 將此頻道設定為 **故事模式**",
                    ephemeral=True
                )
                return

            # 檢查是否已有故事在進行
            db = self.story_manager._get_db(self.guild_id)
            existing_instance = db.get_story_instance(self.channel_id)
            if existing_instance and existing_instance.is_active:
                await interaction.response.send_message(
                    "❌ 這個頻道已經有一個正在進行的故事了！",
                    ephemeral=True
                )
                return

            # 彈出 Modal 收集初始狀態
            from .modals import StoryStartModal
            modal = StoryStartModal(
                story_manager=self.story_manager,
                bot=self.ui_manager.bot,
                guild_id=self.guild_id,
                channel_id=self.channel_id,
                world_name=self.selected_world
            )
            await interaction.response.send_modal(modal)

        except Exception as e:
            self.logger.error(f"開始故事按鈕錯誤: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ 準備開始故事時發生錯誤，請稍後再試",
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
                        description=world.attributes.get('description', '無描述')[:100]
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
            
            character_db = self.story_manager.character_db
            
            # 尋找使用者在此伺服器的角色
            user_characters = character_db.get_characters_by_user(
                interaction.user.id,
                interaction.guild_id
            )
            
            if not user_characters:
                await interaction.followup.send(
                    f"❌ 你在這個伺服器中還沒有創建任何角色。\n"
                    f"請先使用 `/story` 選單中的 '創建角色' 按鈕來創建一個。",
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


class NPCSelectView(discord.ui.View):
    """
    NPC 選擇視圖
    
    讓玩家在開始故事時選擇要參與的 NPC
    """

    @classmethod
    async def create(
        cls,
        story_manager: StoryManager,
        interaction: discord.Interaction,
        channel_id: int,
        world_name: str,
        initial_date: str,
        initial_time: str,
        initial_location: str,
        system_prompt: str,
    ) -> "NPCSelectView":
        """
        非同步工廠方法，用於創建和填充 NPCSelectView。
        """
        logger = logging.getLogger(__name__)
        bot = story_manager.bot
        character_db = story_manager.character_db
        
        # 獲取可選擇的角色列表
        characters = character_db.get_selectable_characters(interaction.guild_id, interaction.user.id)
        logger.debug(f"Found {len(characters)} selectable characters for user {interaction.user.id}")

        # 創建角色選項
        options = []
        for char in characters:
            creator_name = "未知"
            if char.creator_id:
                try:
                    creator = await bot.fetch_user(char.creator_id)
                    creator_name = creator.display_name
                except discord.NotFound:
                    logger.warning(f"Could not find creator user with ID {char.creator_id}")
            
            description = f"創作者: {creator_name}\n{char.description or ''}"
            options.append(discord.SelectOption(
                label=char.name,
                value=char.character_id,
                description=description[:100]
            ))

        # 創建並添加預設旁白選項
        default_narrator_option = discord.SelectOption(
            label="預設旁白 (系統人格)",
            value="_DEFAULT_NARRATOR_",
            description=system_prompt[:100] if system_prompt else "使用當前頻道的系統設定",
            default=True
        )
        options.insert(0, default_narrator_option)

        return cls(
            story_manager=story_manager,
            guild_id=interaction.guild_id,
            channel_id=channel_id,
            world_name=world_name,
            initial_date=initial_date,
            initial_time=initial_time,
            initial_location=initial_location,
            characters=characters,
            options=options,
        )

    def __init__(
        self,
        story_manager: StoryManager,
        guild_id: int,
        channel_id: int,
        world_name: str,
        initial_date: str,
        initial_time: str,
        initial_location: str,
        characters: List[StoryCharacter],
        options: List[discord.SelectOption],
    ):
        super().__init__(timeout=300)
        self.story_manager = story_manager
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.world_name = world_name
        self.initial_date = initial_date
        self.initial_time = initial_time
        self.initial_location = initial_location
        self.characters = characters
        self.logger = logging.getLogger(__name__)

        # 設定 min/max values
        min_val = 1  # 至少要選一個，預設就是旁白
        max_val = len(options)

        self.npc_select = discord.ui.Select(
            custom_id="npc_selector:select_menu",
            placeholder="選擇要參與故事的 NPC (可複選)...",
            min_values=min_val,
            max_values=max_val,
            options=options
        )
        self.add_item(self.npc_select)

    @discord.ui.button(label="✅ 確認開始", style=discord.ButtonStyle.success, row=1, custom_id="npc_selector:confirm_button")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """確認選擇並開始故事"""
        try:
            await interaction.response.defer()

            # 驗證使用者是否至少選擇了一個選項
            if not self.npc_select.values:
                await interaction.followup.send(
                    "請至少選擇一個 NPC 或保留預設旁白來開始故事。",
                    ephemeral=True
                )
                return

            # 添加偵錯日誌，記錄原始返回值
            self.logger.debug(f"NPCSelectView submitted with values: {self.npc_select.values}")

            # 修正過濾邏輯：創建一個只包含真實角色 ID 的新列表
            real_character_ids_str = [
                value for value in self.npc_select.values
                if value != '_DEFAULT_NARRATOR_'
            ]

            # 新增類型轉換邏輯：將字串 ID 列表轉換為整數列表
            character_ids = []
            try:
                character_ids = [int(id_str) for id_str in real_character_ids_str]
            except ValueError:
                self.logger.error("無法將角色 ID 從字串轉換為整數", exc_info=True)
                await interaction.response.send_message("處理角色選擇時發生內部錯誤，請聯繫管理員。", ephemeral=True)
                return

            db = self.story_manager._get_db(self.guild_id)
            db.initialize()

            # 創建新的故事實例
            new_instance = StoryInstance(
                channel_id=self.channel_id,
                guild_id=self.guild_id,
                world_name=self.world_name,
                current_date=self.initial_date,
                current_time=self.initial_time,
                current_location=self.initial_location,
                active_character_ids=character_ids
            )
            
            # 初始化預設狀態，這可能會覆蓋使用者輸入
            new_instance = self.story_manager.state_manager.initialize_default_state(new_instance)
            
            # 重新應用使用者輸入的初始狀態，以防被覆蓋
            new_instance.current_date = self.initial_date
            new_instance.current_time = self.initial_time
            new_instance.current_location = self.initial_location
            
            db.save_story_instance(new_instance)
            self.logger.debug(f"Saved new story instance {new_instance.channel_id} to DB.")

            # 載入世界資訊
            world = db.get_world(self.world_name)
            if not world:
                self.logger.error(f"FATAL: Could not find world '{self.world_name}' after starting story.")
                await interaction.edit_original_response(content="❌ 無法載入世界資料，故事無法開始。", embed=None, view=None)
                return
            
            # 發送成功訊息到頻道（公開）
            embed = discord.Embed(
                title="🎬 故事開始！",
                description=f"**{self.world_name}** 的冒險篇章已在此頻道開啟！",
                color=discord.Color.gold()
            )
            world_background = world.attributes.get('background', '這個世界沒有背景描述。')
            embed.add_field(
                name="🌍 世界背景",
                value=world_background[:800] + ("..." if len(world_background) > 800 else ""),
                inline=False
            )
            embed.add_field(name="📅 日期", value=self.initial_date, inline=True)
            embed.add_field(name="⏰ 時間", value=self.initial_time, inline=True)
            embed.add_field(name="📍 地點", value=self.initial_location, inline=False)
            
            if character_ids:
                # 確保這裡比較的是整數 ID
                selected_npcs = [char.name for char in self.characters if char.character_id in character_ids]
                embed.add_field(
                    name="👥 參與的NPC",
                    value=", ".join(selected_npcs) if selected_npcs else "無",
                    inline=False
                )

            embed.set_footer(text="💡 在此頻道輸入訊息來與故事互動")
            
            # 編輯原始的臨時訊息
            await interaction.edit_original_response(content=None, embed=embed, view=None)
            self.logger.info(f"Story started successfully in channel {self.channel_id}")

        except Exception as e:
            self.logger.error("Error in NPCSelectView confirm_button", exc_info=True)
            if not interaction.response.is_done():
                await interaction.edit_original_response(
                    content="❌ 開始故事時發生嚴重錯誤，請聯繫管理員。",
                    embed=None,
                    view=None
                )