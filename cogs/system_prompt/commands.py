"""
頻道系統提示管理模組的 Discord 斜線命令

提供完整的 Discord 斜線命令介面，包含所有系統提示管理功能。
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Dict, Any, List
import asyncio
import functools
from addons.logging import get_logger

from .manager import SystemPromptManager
from .permissions import PermissionValidator
from .exceptions import (
    SystemPromptError,
    PermissionError,
    ValidationError,
)
from function import func
import asyncio


def handle_system_prompt_error(func):
    """系統提示錯誤處理裝飾器"""
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any):
        interaction = args[1] if len(args) > 1 else kwargs.get('interaction')
        # 取得語言管理器
        lang_manager = interaction.client.get_cog("LanguageManager")
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        
        try:
            return await func(*args, **kwargs)
        except PermissionError as e:
            error_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "errors", "permission_denied") if lang_manager else "權限不足"
            full_message = f"❌ {error_msg}" if not str(e) else f"❌ {error_msg}: {str(e)}"
            
            if not interaction.response.is_done():
                await interaction.response.send_message(full_message, ephemeral=True)
            else:
                await interaction.followup.send(full_message, ephemeral=True)
        except ValidationError as e:
            error_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "errors", "validation_failed") if lang_manager else "驗證失敗"
            full_message = f"❌ {error_msg}: {str(e)}"
            
            if not interaction.response.is_done():
                await interaction.response.send_message(full_message, ephemeral=True)
            else:
                await interaction.followup.send(full_message, ephemeral=True)
        except SystemPromptError as e:
            error_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "errors", "operation_failed") if lang_manager else "操作失敗"
            full_message = f"❌ {error_msg}: {str(e)}"
            
            if not interaction.response.is_done():
                await interaction.response.send_message(full_message, ephemeral=True)
            else:
                await interaction.followup.send(full_message, ephemeral=True)
        except Exception as e:
            await func.report_error(e, "System prompt operation error")
            # Create local logger for error context
            local_log = get_logger(source=__name__, server_id="system")
            bound_log = local_log.bind(server_id=str(interaction.guild_id) if interaction.guild else "system", user_id=str(interaction.user.id))
            bound_log.error(f"System prompt operation error: {str(e)}")
            
            error_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "errors", "system_error") if lang_manager else "系統錯誤，請稍後再試"
            
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)
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
        self.logger = get_logger(source=__name__, server_id="system")
        self.manager = SystemPromptManager(bot)
        
        # 設定語言管理器
        try:
            language_manager = bot.get_cog("LanguageManager")
            self.manager.language_manager = language_manager
            if language_manager:
                self.logger.debug("✅ 語言管理器已設定")
            else:
                self.logger.warning("⚠️ 語言管理器未找到")
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error setting language manager"))
            self.logger.warning(f"設定語言管理器時發生錯誤: {e}")
        
        self.permission_validator = PermissionValidator(bot)
    
    def get_system_prompt_manager(self) -> SystemPromptManager:
        """取得系統提示管理器實例"""
        return self.manager
    
    @app_commands.command(name="system_prompt", description="系統提示管理 - 統一管理介面")
    @handle_system_prompt_error
    async def system_prompt(self, interaction: discord.Interaction):
        """統一的系統提示管理命令 - 主選單介面"""
        
        # 導入統一 UI 元件
        from .views import SystemPromptMainView
        
        # 建立主選單 View
        main_view = SystemPromptMainView(
            manager=self.manager,
            permission_validator=self.permission_validator
        )

        # 取得翻譯文字
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        lang_manager = self.bot.get_cog("LanguageManager")
        
        if lang_manager:
            title = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "main_menu", "title")
            description = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "main_menu", "description")
            main_functions_title = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "main_menu", "main_functions_title")
            main_functions_description = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "main_menu", "main_functions_description")
            usage_title = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "main_menu", "usage_title")
            usage_description = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "main_menu", "usage_description")
            footer = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "main_menu", "footer")
        else:
            # 降級到預設值（使用英文回退）
            title = "🤖 System Prompt Management"
            description = "Welcome to the unified system prompt management interface! Please select the function to execute:"
            main_functions_title = "🔧 Main Functions"
            main_functions_description = (
                "• **Set Prompt** - Set channel or server system prompts\n"
                "• **View Config** - View current system prompt configuration\n"
                "• **Module Edit** - Edit specific YAML modules\n"
                "• **Copy Prompt** - Copy system prompts to other channels\n"
                "• **Remove Prompt** - Remove configured system prompts\n"
                "• **Reset Config** - Reset system prompt configuration"
            )
            usage_title = "📋 Usage Instructions"
            usage_description = (
                "Click the buttons below to execute corresponding functions.\n"
                "System supports 3-layer inheritance: YAML base → server default → channel specific"
            )
            footer = "Note: All operations include permission checks for security"

        # 建立主選單 Embed
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )

        # 添加功能說明
        embed.add_field(
            name=main_functions_title,
            value=main_functions_description,
            inline=False
        )

        embed.add_field(
            name=usage_title,
            value=usage_description,
            inline=False
        )

        embed.set_footer(text=footer)

        # 發送主選單
        await interaction.response.send_message(
            embed=embed,
            view=main_view,
            ephemeral=True
        )


async def setup(bot):
    """設定函式，用於載入 Cog"""
    await bot.add_cog(SystemPromptCommands(bot))