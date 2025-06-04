import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import time
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from .language_manager import LanguageManager
from addons.settings import TOKENS

class ChannelManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = "data/channel_configs"
        self.lang_manager: Optional[LanguageManager] = None
        self.tokens = TOKENS()  # 初始化 TOKENS 實例以獲取 BOT_OWNER_ID
        os.makedirs(self.data_dir, exist_ok=True)

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    def get_config_path(self, guild_id):
        return os.path.join(self.data_dir, f"{guild_id}.json")

    def load_config(self, guild_id):
        """載入伺服器配置"""
        config_path = self.get_config_path(guild_id)
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                # 確保必要的鍵值存在
                if "auto_response" not in config:
                    config["auto_response"] = {}
                return config
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._get_default_config()
        else:
            return self._get_default_config()

    def _get_default_config(self):
        """取得預設配置"""
        return {
            "mode": "unrestricted",
            "whitelist": [],
            "blacklist": [],
            "auto_response": {}
        }

    def save_config(self, guild_id, config):
        """儲存伺服器配置"""
        config_path = self.get_config_path(guild_id)
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save config for guild {guild_id}: {e}")

    async def check_admin_permissions(self, interaction: discord.Interaction) -> bool:
        """檢查是否有管理員權限"""
        # 使用設定檔中的 BOT_OWNER_ID，如果設定檔中沒有則使用預設值
        bot_owner_id = getattr(self.tokens, 'bot_owner_id', 0)
        if interaction.user.guild_permissions.administrator or interaction.user.id == bot_owner_id:
            return True
        
        # 使用翻譯系統
        if self.lang_manager:
            error_message = self.lang_manager.translate(
                str(interaction.guild_id),
                "errors",
                "permission_denied"
            )
        else:
            # 備用訊息，當語言管理器尚未初始化時
            error_message = "您沒有權限執行此操作，僅限管理員使用此命令。"
        
        await interaction.response.send_message(error_message, ephemeral=True)
        return False

    @app_commands.command(name="set_channel_mode", description="設定頻道回應模式")
    @app_commands.choices(mode=[
        app_commands.Choice(name="無限制", value="unrestricted"),
        app_commands.Choice(name="白名單", value="whitelist"),
        app_commands.Choice(name="黑名單", value="blacklist")
    ])
    async def set_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        # 檢查權限
        if not await self.check_admin_permissions(interaction):
            return
            
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        config["mode"] = mode.value
        self.save_config(guild_id, config)
        
        # 使用翻譯系統
        if self.lang_manager:
            # 獲取模式的翻譯名稱
            mode_name = self.lang_manager.translate(
                guild_id,
                "commands",
                "set_channel_mode",
                "choices",
                mode.value
            )
            success_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "set_channel_mode",
                "responses",
                "success",
                mode=mode_name
            )
        else:
            # 備用訊息
            success_message = f"已將頻道回應模式設定為：{mode.name}"
        
        await interaction.response.send_message(success_message)

    @app_commands.command(name="add_channel", description="新增頻道到白名單或黑名單")
    @app_commands.choices(list_type=[
        app_commands.Choice(name="白名單", value="whitelist"),
        app_commands.Choice(name="黑名單", value="blacklist")
    ])
    async def add_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel, list_type: app_commands.Choice[str]):
        # 檢查權限
        if not await self.check_admin_permissions(interaction):
            return
            
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        
        # 使用翻譯系統
        if self.lang_manager:
            list_type_name = self.lang_manager.translate(
                guild_id,
                "commands",
                "add_channel",
                "choices",
                list_type.value
            )
        else:
            list_type_name = list_type.name
        
        if channel_id not in config[list_type.value]:
            config[list_type.value].append(channel_id)
            self.save_config(guild_id, config)
            
            if self.lang_manager:
                success_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "add_channel",
                    "responses",
                    "success",
                    channel=f"<#{channel_id}>",
                    list_type=list_type_name
                )
            else:
                success_message = f"已將頻道 <#{channel_id}> 新增到 {list_type_name}"
            
            await interaction.response.send_message(success_message)
        else:
            if self.lang_manager:
                exists_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "add_channel",
                    "responses",
                    "already_exists",
                    channel=f"<#{channel_id}>",
                    list_type=list_type_name
                )
            else:
                exists_message = f"頻道 <#{channel_id}> 已存在於 {list_type_name}"
            
            await interaction.response.send_message(exists_message)

    @app_commands.command(name="remove_channel", description="移除頻道從白名單或黑名單")
    @app_commands.choices(list_type=[
        app_commands.Choice(name="白名單", value="whitelist"),
        app_commands.Choice(name="黑名單", value="blacklist")
    ])
    async def remove_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel, list_type: app_commands.Choice[str]):
        # 檢查權限
        if not await self.check_admin_permissions(interaction):
            return
            
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        
        # 使用翻譯系統
        if self.lang_manager:
            list_type_name = self.lang_manager.translate(
                guild_id,
                "commands",
                "remove_channel",
                "choices",
                list_type.value
            )
        else:
            list_type_name = list_type.name
        
        if channel_id in config[list_type.value]:
            config[list_type.value].remove(channel_id)
            self.save_config(guild_id, config)
            
            if self.lang_manager:
                success_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "remove_channel",
                    "responses",
                    "success",
                    channel=f"<#{channel_id}>",
                    list_type=list_type_name
                )
            else:
                success_message = f"已將頻道 <#{channel_id}> 移除從 {list_type_name}"
            
            await interaction.response.send_message(success_message)
        else:
            if self.lang_manager:
                not_found_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "remove_channel",
                    "responses",
                    "not_found",
                    channel=f"<#{channel_id}>",
                    list_type=list_type_name
                )
            else:
                not_found_message = f"頻道 <#{channel_id}> 不存在於 {list_type_name}"
            
            await interaction.response.send_message(not_found_message)

    @app_commands.command(name="auto_response", description="設定頻道自動回覆")
    async def auto_response_command(self, interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool):
        # 檢查權限
        if not await self.check_admin_permissions(interaction):
            return
            
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        config["auto_response"][channel_id] = enabled
        self.save_config(guild_id, config)
        
        # 使用翻譯系統
        if self.lang_manager:
            success_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "auto_response",
                "responses",
                "success",
                channel=f"<#{channel_id}>",
                enabled=str(enabled)
            )
        else:
            # 備用訊息
            success_message = f"已將頻道 <#{channel_id}> 自動回覆設定為：{enabled}"
        
        await interaction.response.send_message(success_message)

    def is_allowed_channel(self, channel: discord.TextChannel, guild_id: str):
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        mode = config.get("mode", "unrestricted")
        auto_response_enabled = config["auto_response"].get(channel_id, False)

        if mode == "unrestricted":
            return True, auto_response_enabled
        elif mode == "whitelist":
            return channel_id in config.get("whitelist", []), auto_response_enabled
        elif mode == "blacklist":
            return channel_id not in config.get("blacklist", []), auto_response_enabled
        return False, False


async def setup(bot):
    await bot.add_cog(ChannelManager(bot))
