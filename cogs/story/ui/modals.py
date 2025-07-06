import discord
import logging
from typing import Optional

from ..manager import StoryManager
from ..models import StoryWorld, StoryCharacter, StoryInstance


class WorldCreateModal(discord.ui.Modal):
    """
    世界創建 Modal
    
    提供表單介面讓使用者輸入新世界的名稱和背景故事
    """
    
    def __init__(self, story_manager: StoryManager, guild_id: int):
        super().__init__(title="🌍 創建新的故事世界")
        self.story_manager = story_manager
        self.guild_id = guild_id
        self.logger = logging.getLogger(__name__)
    
    world_name = discord.ui.TextInput(
        label="世界名稱",
        placeholder="輸入你的世界名稱（例如：中土世界、賽博朋克 2077）",
        max_length=50,
        required=True
    )
    
    background = discord.ui.TextInput(
        label="世界背景",
        placeholder="描述這個世界的背景故事、設定和特色...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """處理世界創建表單提交"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 檢查世界名稱是否已存在
            db = self.story_manager._get_db(self.guild_id)
            db.initialize()

            existing_world = db.get_world(self.world_name.value)
            if existing_world:
                await interaction.followup.send(
                    f"❌ 名為 `{self.world_name.value}` 的世界已經存在。請選擇其他名稱。",
                    ephemeral=True
                )
                return
            
            # 創建新世界
            new_world = StoryWorld(
                guild_id=self.guild_id,
                world_name=self.world_name.value,
                background=self.background.value
            )
            
            db.save_world(new_world)
            
            # 成功回應
            embed = discord.Embed(
                title="✅ 世界創建成功！",
                description=f"**{self.world_name.value}** 已成功創建",
                color=discord.Color.green()
            )
            embed.add_field(
                name="🌍 世界名稱", 
                value=self.world_name.value, 
                inline=False
            )
            embed.add_field(
                name="📖 背景故事", 
                value=self.background.value[:500] + ("..." if len(self.background.value) > 500 else ""),
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"創建世界時發生錯誤: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ 創建世界時發生錯誤，請稍後再試。",
                ephemeral=True
            )
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """處理 Modal 錯誤"""
        self.logger.error(f"WorldCreateModal 錯誤: {error}", exc_info=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ 處理請求時發生錯誤",
                    ephemeral=True
                )
        except:
            pass


class CharacterCreateModal(discord.ui.Modal):
    """
    角色創建 Modal
    
    提供表單介面讓使用者創建新角色
    """
    
    def __init__(self, story_manager: StoryManager, guild_id: int, world_name: Optional[str] = None, name: str = "", description: str = ""):
        super().__init__(title="👤 創建新角色")
        self.story_manager = story_manager
        self.guild_id = guild_id
        self.world_name = world_name
        self.logger = logging.getLogger(__name__)

        self.character_name = discord.ui.TextInput(
            label="角色名稱",
            placeholder="輸入你的角色名稱",
            max_length=50,
            required=True,
            default=name
        )
        
        self.description = discord.ui.TextInput(
            label="角色描述",
            placeholder="描述角色的外觀、背景、性格等...",
            style=discord.TextStyle.paragraph,
            max_length=800,
            required=True,
            default=description
        )

        self.webhook_url = discord.ui.TextInput(
            label="角色 Webhook 網址 (選填)",
            placeholder="請貼上 Discord Webhook 的 URL...",
            required=False,
            style=discord.TextStyle.short
        )
        
        self.add_item(self.character_name)
        self.add_item(self.description)
        self.add_item(self.webhook_url)
    
    async def on_submit(self, interaction: discord.Interaction):
        """處理角色創建表單提交"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            db = self.story_manager._get_db(self.guild_id)
            db.initialize()
            
            # 如果沒有指定世界，需要使用者選擇
            if not self.world_name:
                worlds = db.get_all_worlds()
                if not worlds:
                    await interaction.followup.send(
                        "❌ 沒有可用的世界。請先創建一個世界後再創建角色。",
                        ephemeral=True
                    )
                    return
                # 如果只有一個世界，自動選擇
                if len(worlds) == 1:
                    self.world_name = worlds[0].world_name
                else:
                    # 多個世界的情況下，需要額外的選擇邏輯
                    # 這裡暫時選擇第一個世界，實際實作中可能需要額外的選擇步驟
                    self.world_name = worlds[0].world_name
            
            # 檢查世界是否存在
            world = db.get_world(self.world_name)
            if not world:
                await interaction.followup.send(
                    f"❌ 找不到世界 `{self.world_name}`",
                    ephemeral=True
                )
                return
            
            # 創建新角色
            new_character = StoryCharacter(
                world_name=self.world_name,
                name=self.character_name.value,
                description=self.description.value,
                webhook_url=self.webhook_url.value or None,
                is_pc=True,  # 玩家角色
                user_id=interaction.user.id
            )
            
            db.save_character(new_character)
            
            # 成功回應
            embed = discord.Embed(
                title="✅ 角色創建成功！",
                description=f"**{self.character_name.value}** 已在 **{self.world_name}** 世界中誕生",
                color=discord.Color.green()
            )
            embed.add_field(
                name="👤 角色名稱", 
                value=self.character_name.value, 
                inline=True
            )
            embed.add_field(
                name="🌍 所屬世界", 
                value=self.world_name, 
                inline=True
            )
            embed.add_field(
                name="📝 角色描述", 
                value=self.description.value[:300] + ("..." if len(self.description.value) > 300 else ""),
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"創建角色時發生錯誤: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ 創建角色時發生錯誤，請稍後再試。",
                ephemeral=True
            )
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """處理 Modal 錯誤"""
        self.logger.error(f"CharacterCreateModal 錯誤: {error}", exc_info=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ 處理請求時發生錯誤",
                    ephemeral=True
                )
        except:
            pass


class StoryStartModal(discord.ui.Modal):
    """
    故事開始 Modal

    收集故事開始時的初始世界狀態
    """

    def __init__(self, story_manager: StoryManager, guild_id: int, channel_id: int, world_name: str):
        super().__init__(title="🎬 設定故事初始狀態")
        self.story_manager = story_manager
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.world_name = world_name
        self.logger = logging.getLogger(__name__)

    initial_date = discord.ui.TextInput(
        label="初始日期",
        placeholder="例如：晴天，2024年7月7日",
        required=True
    )

    initial_time = discord.ui.TextInput(
        label="初始時間",
        placeholder="例如：上午9:00",
        required=True
    )

    initial_location = discord.ui.TextInput(
        label="初始地點",
        placeholder="例如：寧靜的森林小徑上",
        required=True,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        """處理表單提交，創建故事實例"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            db = self.story_manager._get_db(self.guild_id)
            db.initialize()

            # 創建新的故事實例
            new_instance = StoryInstance(
                channel_id=self.channel_id,
                guild_id=self.guild_id,
                world_name=self.world_name,
                current_date=self.initial_date.value,
                current_time=self.initial_time.value,
                current_location=self.initial_location.value
            )
            
            # 初始化預設狀態
            new_instance = self.story_manager.state_manager.initialize_default_state(new_instance)
            db.save_story_instance(new_instance)

            # 載入世界資訊
            world = db.get_world(self.world_name)
            
            # 發送成功訊息到頻道（公開）
            embed = discord.Embed(
                title="🎬 故事開始！",
                description=f"**{self.world_name}** 的冒險篇章已在此頻道開啟！",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="🌍 世界背景",
                value=world.background[:800] + ("..." if len(world.background) > 800 else ""),
                inline=False
            )
            embed.add_field(name="📅 日期", value=self.initial_date.value, inline=True)
            embed.add_field(name="⏰ 時間", value=self.initial_time.value, inline=True)
            embed.add_field(name="📍 地點", value=self.initial_location.value, inline=False)
            embed.set_footer(text="💡 在此頻道輸入訊息來與故事互動")
            
            await interaction.channel.send(embed=embed)
            
            # 私人確認訊息
            await interaction.followup.send(
                f"✅ 故事已成功在此頻道開始！\n🌍 世界：**{self.world_name}**",
                ephemeral=True
            )

        except Exception as e:
            self.logger.error(f"開始故事時發生錯誤: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ 開始故事時發生錯誤，請稍後再試。",
                ephemeral=True
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """處理 Modal 錯誤"""
        self.logger.error(f"StoryStartModal 錯誤: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ 處理請求時發生錯誤", ephemeral=True)