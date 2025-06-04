"""
頻道系統提示管理模組的 Discord 斜線命令

提供完整的 Discord 斜線命令介面，包含所有系統提示管理功能。
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, Dict, Any, List
import asyncio
import functools

from .manager import SystemPromptManager
from .permissions import PermissionValidator
from .ui import (
    SystemPromptModal,
    ConfirmationView,
    ChannelSelectView,
    ModuleSelectView,
    create_system_prompt_embed
)
from .exceptions import (
    SystemPromptError,
    PermissionError,
    ValidationError,
    PromptNotFoundError
)


def handle_system_prompt_error(func):
    """系統提示錯誤處理裝飾器"""
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any):
        interaction = args[1] if len(args) > 1 else kwargs.get('interaction')
        try:
            return await func(*args, **kwargs)
        except PermissionError as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ 權限不足：{str(e)}", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ 權限不足：{str(e)}", ephemeral=True
                )
        except ValidationError as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ 驗證失敗：{str(e)}", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ 驗證失敗：{str(e)}", ephemeral=True
                )
        except SystemPromptError as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ 操作失敗：{str(e)}", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ 操作失敗：{str(e)}", ephemeral=True
                )
        except Exception as e:
            logging.error(f"系統提示操作錯誤: {str(e)}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ 系統錯誤，請稍後再試", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ 系統錯誤，請稍後再試", ephemeral=True
                )
    return wrapper


class SystemPromptCommands(commands.Cog):
    """系統提示管理命令類別"""
    
    def __init__(self, bot: discord.Client):
        """
        初始化命令類別
        
        Args:
            bot: Discord 機器人實例
        """
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.manager = SystemPromptManager(bot)
        self.permission_validator = PermissionValidator(bot)
    
    def get_system_prompt_manager(self) -> SystemPromptManager:
        """取得系統提示管理器實例"""
        return self.manager
    
    # 系統提示群組命令
    system_prompt_group = app_commands.Group(
        name="system_prompt",
        description="管理系統提示設定"
    )
    
    @system_prompt_group.command(name="set", description="設定系統提示")
    @app_commands.describe(
        type="設定類型（頻道特定或伺服器預設）",
        channel="目標頻道（設定頻道特定時使用）",
        content="系統提示內容（選填，留空將開啟編輯器）"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="頻道特定", value="channel"),
        app_commands.Choice(name="伺服器預設", value="server")
    ])
    @handle_system_prompt_error
    async def set_prompt(self, 
                        interaction: discord.Interaction,
                        type: str,
                        channel: Optional[discord.TextChannel] = None,
                        content: Optional[str] = None):
        """設定系統提示"""
        
        # 權限檢查
        if type == "channel":
            if not channel:
                channel = interaction.channel
            
            self.permission_validator.validate_permission_or_raise(
                interaction.user, 'modify_channel', channel
            )
            
            target_channel = channel
            scope_text = f"頻道 #{channel.name}"
            
        else:  # server
            self.permission_validator.validate_permission_or_raise(
                interaction.user, 'modify_server', interaction.guild
            )
            
            target_channel = None
            scope_text = "伺服器預設"
        
        # 如果沒有提供內容，開啟 Modal 編輯器
        if not content:
            # 取得現有內容
            if type == "channel":
                config = self.manager._load_guild_config(str(interaction.guild.id))
                existing_content = ""
                system_prompts = config.get('system_prompts', {})
                channels = system_prompts.get('channels', {})
                if str(channel.id) in channels:
                    existing_content = channels[str(channel.id)].get('prompt', '')
            else:
                config = self.manager._load_guild_config(str(interaction.guild.id))
                existing_content = ""
                system_prompts = config.get('system_prompts', {})
                server_level = system_prompts.get('server_level', {})
                existing_content = server_level.get('prompt', '')
            
            modal = SystemPromptModal(
                title=f"設定{scope_text}系統提示",
                initial_value=existing_content,
                callback_func=lambda i, prompt: self._handle_set_modal(
                    i, type, target_channel, prompt
                )
            )
            
            await interaction.response.send_modal(modal)
        else:
            # 直接設定內容
            await self._set_prompt_content(interaction, type, target_channel, content)
    
    async def _handle_set_modal(self, 
                               interaction: discord.Interaction,
                               type: str,
                               channel: Optional[discord.TextChannel],
                               content: str):
        """處理設定 Modal 回調"""
        await self._set_prompt_content(interaction, type, channel, content)
    
    async def _set_prompt_content(self,
                                 interaction: discord.Interaction,
                                 type: str,
                                 channel: Optional[discord.TextChannel],
                                 content: str):
        """實際設定提示內容"""
        try:
            prompt_data = {'prompt': content}
            
            if type == "channel":
                success = self.manager.set_channel_prompt(
                    str(interaction.guild.id),
                    str(channel.id),
                    prompt_data,
                    str(interaction.user.id)
                )
                scope_text = f"頻道 #{channel.name}"
            else:
                success = self.manager.set_server_prompt(
                    str(interaction.guild.id),
                    prompt_data,
                    str(interaction.user.id)
                )
                scope_text = "伺服器預設"
            
            if success:
                embed = discord.Embed(
                    title="✅ 系統提示設定成功",
                    description=f"已成功設定{scope_text}的系統提示",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="內容長度",
                    value=f"{len(content)} 字元",
                    inline=True
                )
                embed.add_field(
                    name="設定者",
                    value=interaction.user.mention,
                    inline=True
                )
                
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"設定系統提示時發生錯誤: {e}")
            raise SystemPromptError(f"設定失敗: {str(e)}")
    
    @system_prompt_group.command(name="view", description="查看系統提示配置")
    @app_commands.describe(
        channel="目標頻道（可選）",
        show_inherited="顯示繼承的提示"
    )
    @handle_system_prompt_error
    async def view_prompt(self,
                         interaction: discord.Interaction,
                         channel: Optional[discord.TextChannel] = None,
                         show_inherited: bool = True):
        """查看系統提示配置"""
        
        if not channel:
            channel = interaction.channel
        
        # 權限檢查
        self.permission_validator.validate_permission_or_raise(
            interaction.user, 'view', channel
        )
        
        try:
            # 取得有效提示
            prompt_data = self.manager.get_effective_prompt(
                str(channel.id),
                str(interaction.guild.id),
                None  # 不需要 message 物件
            )
            
            # 建立 Embed
            embed = create_system_prompt_embed(prompt_data, channel)
            
            # 檢查是否可編輯
            can_edit = self.permission_validator.can_modify_channel_prompt(
                interaction.user, channel
            )
            
            # 如果顯示繼承資訊
            if show_inherited:
                config = self.manager._load_guild_config(str(interaction.guild.id))
                system_prompts = config.get('system_prompts', {})
                
                # 檢查各層級的提示
                inheritance_info = []
                
                # YAML 基礎
                inheritance_info.append("🔹 YAML 基礎提示")
                
                # 伺服器級別
                server_level = system_prompts.get('server_level', {})
                if server_level.get('prompt'):
                    inheritance_info.append("🔸 伺服器預設提示")
                
                # 頻道級別
                channels = system_prompts.get('channels', {})
                if str(channel.id) in channels:
                    channel_config = channels[str(channel.id)]
                    if channel_config.get('prompt'):
                        inheritance_info.append("🔸 頻道特定提示")
                
                embed.add_field(
                    name="繼承層級",
                    value="\n".join(inheritance_info) if inheritance_info else "僅 YAML 基礎",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"查看系統提示時發生錯誤: {e}")
            raise SystemPromptError(f"查看失敗: {str(e)}")
    
    @system_prompt_group.command(name="remove", description="移除系統提示")
    @app_commands.describe(
        type="移除類型",
        channel="目標頻道（移除頻道特定時使用）"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="頻道特定", value="channel"),
        app_commands.Choice(name="伺服器預設", value="server")
    ])
    @handle_system_prompt_error
    async def remove_prompt(self,
                           interaction: discord.Interaction,
                           type: str,
                           channel: Optional[discord.TextChannel] = None):
        """移除系統提示"""
        
        # 權限檢查和設定
        if type == "channel":
            if not channel:
                channel = interaction.channel
            
            self.permission_validator.validate_permission_or_raise(
                interaction.user, 'modify_channel', channel
            )
            
            scope_text = f"頻道 #{channel.name}"
            confirm_text = f"確定要移除頻道 #{channel.name} 的系統提示嗎？"
            
        else:  # server
            self.permission_validator.validate_permission_or_raise(
                interaction.user, 'modify_server', interaction.guild
            )
            
            scope_text = "伺服器預設"
            confirm_text = "確定要移除伺服器預設系統提示嗎？"
        
        # 確認對話框
        embed = discord.Embed(
            title="⚠️ 確認移除",
            description=confirm_text,
            color=discord.Color.orange()
        )
        
        view = ConfirmationView(
            confirm_text="確認移除",
            cancel_text="取消"
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        # 等待確認
        await view.wait()
        
        if view.result:
            try:
                if type == "channel":
                    success = self.manager.remove_channel_prompt(
                        str(interaction.guild.id),
                        str(channel.id)
                    )
                else:
                    success = self.manager.remove_server_prompt(
                        str(interaction.guild.id)
                    )
                
                if success:
                    embed = discord.Embed(
                        title="✅ 移除成功",
                        description=f"已成功移除{scope_text}的系統提示",
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                
            except PromptNotFoundError:
                await interaction.followup.send(
                    f"❌ 未找到{scope_text}的系統提示", ephemeral=True
                )
            except Exception as e:
                self.logger.error(f"移除系統提示時發生錯誤: {e}")
                await interaction.followup.send(
                    f"❌ 移除失敗: {str(e)}", ephemeral=True
                )
    
    @system_prompt_group.command(name="copy", description="複製系統提示到其他頻道")
    @app_commands.describe(
        from_channel="來源頻道",
        to_channel="目標頻道"
    )
    @handle_system_prompt_error
    async def copy_prompt(self,
                         interaction: discord.Interaction,
                         from_channel: discord.TextChannel,
                         to_channel: discord.TextChannel):
        """複製系統提示到其他頻道"""
        
        # 權限檢查
        self.permission_validator.validate_permission_or_raise(
            interaction.user, 'modify_channel', to_channel
        )
        
        if from_channel.id == to_channel.id:
            await interaction.response.send_message(
                "❌ 來源頻道和目標頻道不能相同", ephemeral=True
            )
            return
        
        try:
            # 檢查目標頻道是否已有提示
            config = self.manager._load_guild_config(str(interaction.guild.id))
            system_prompts = config.get('system_prompts', {})
            channels = system_prompts.get('channels', {})
            
            target_has_prompt = str(to_channel.id) in channels
            
            confirm_text = f"複製 #{from_channel.name} 的系統提示到 #{to_channel.name}"
            if target_has_prompt:
                confirm_text += "\n⚠️ 目標頻道已有系統提示，將會被覆蓋"
            
            # 確認對話框
            embed = discord.Embed(
                title="🔄 確認複製",
                description=confirm_text,
                color=discord.Color.blue()
            )
            
            view = ConfirmationView(
                confirm_text="確認複製",
                cancel_text="取消",
                confirm_style=discord.ButtonStyle.primary
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            # 等待確認
            await view.wait()
            
            if view.result:
                success = self.manager.copy_channel_prompt(
                    str(interaction.guild.id), str(from_channel.id),
                    str(interaction.guild.id), str(to_channel.id)
                )
                
                if success:
                    embed = discord.Embed(
                        title="✅ 複製成功",
                        description=f"已成功將 #{from_channel.name} 的系統提示複製到 #{to_channel.name}",
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
            
        except PromptNotFoundError:
            await interaction.followup.send(
                f"❌ 來源頻道 #{from_channel.name} 沒有設定系統提示", ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"複製系統提示時發生錯誤: {e}")
            await interaction.followup.send(
                f"❌ 複製失敗: {str(e)}", ephemeral=True
            )
    
    @system_prompt_group.command(name="reset", description="重置系統提示")
    @app_commands.describe(
        type="重置類型"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="當前頻道", value="channel"),
        app_commands.Choice(name="伺服器預設", value="server"),
        app_commands.Choice(name="全部重置", value="all")
    ])
    @handle_system_prompt_error
    async def reset_prompt(self,
                          interaction: discord.Interaction,
                          type: str):
        """重置系統提示"""
        
        # 權限檢查
        if type == "channel":
            self.permission_validator.validate_permission_or_raise(
                interaction.user, 'modify_channel', interaction.channel
            )
            confirm_text = f"確定要重置頻道 #{interaction.channel.name} 的系統提示嗎？"
            
        elif type == "server":
            self.permission_validator.validate_permission_or_raise(
                interaction.user, 'modify_server', interaction.guild
            )
            confirm_text = "確定要重置伺服器預設系統提示嗎？"
            
        else:  # all
            self.permission_validator.validate_permission_or_raise(
                interaction.user, 'modify_server', interaction.guild
            )
            confirm_text = "確定要重置所有系統提示設定嗎？\n⚠️ 此操作無法復原！"
        
        # 確認對話框
        embed = discord.Embed(
            title="⚠️ 確認重置",
            description=confirm_text,
            color=discord.Color.red()
        )
        
        view = ConfirmationView(
            confirm_text="確認重置",
            cancel_text="取消"
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        # 等待確認
        await view.wait()
        
        if view.result:
            try:
                if type == "channel":
                    success = self.manager.remove_channel_prompt(
                        str(interaction.guild.id),
                        str(interaction.channel.id)
                    )
                    result_text = f"頻道 #{interaction.channel.name}"
                    
                elif type == "server":
                    success = self.manager.remove_server_prompt(
                        str(interaction.guild.id)
                    )
                    result_text = "伺服器預設"
                    
                else:  # all
                    config = self.manager._get_default_config()
                    self.manager._save_guild_config(str(interaction.guild.id), config)
                    self.manager.clear_cache(str(interaction.guild.id))
                    success = True
                    result_text = "所有"
                
                if success:
                    embed = discord.Embed(
                        title="✅ 重置成功",
                        description=f"已成功重置{result_text}系統提示設定",
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                
            except PromptNotFoundError:
                await interaction.followup.send(
                    "❌ 未找到要重置的系統提示", ephemeral=True
                )
            except Exception as e:
                self.logger.error(f"重置系統提示時發生錯誤: {e}")
                await interaction.followup.send(
                    f"❌ 重置失敗: {str(e)}", ephemeral=True
                )
    
    @system_prompt_group.command(name="modules", description="查看可用的模組列表")
    @handle_system_prompt_error
    async def list_modules(self, interaction: discord.Interaction):
        """查看可用的模組列表"""
        
        try:
            modules = self.manager.get_available_modules()
            
            embed = discord.Embed(
                title="📦 可用模組列表",
                description="以下是可以覆蓋的 YAML 系統提示模組：",
                color=discord.Color.blue()
            )
            
            if modules:
                module_text = "\n".join([f"• `{module}`" for module in modules])
                embed.add_field(
                    name="模組名稱",
                    value=module_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="模組名稱",
                    value="暫無可用模組",
                    inline=False
                )
            
            embed.add_field(
                name="使用方式",
                value="在設定系統提示時，可以使用模組覆蓋功能來自訂特定模組的內容",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"取得模組列表時發生錯誤: {e}")
            raise SystemPromptError(f"無法取得模組列表: {str(e)}")


async def setup(bot):
    """設定函式，用於載入 Cog"""
    await bot.add_cog(SystemPromptCommands(bot))