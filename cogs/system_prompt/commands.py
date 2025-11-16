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
from .exceptions import (
    SystemPromptError,
    PermissionError,
    ValidationError,
)
from function import func
import asyncio

from utils.logger import LoggerMixin

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
            await func.report_error(e, "System prompt operation error")
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


class SystemPromptCommands(commands.Cog, LoggerMixin):
    """系統提示管理命令類別"""
    
    def __init__(self, bot: discord.Client):
        LoggerMixin.__init__(self, "SystemPromptCommands")
        """
        初始化命令類別
        
        Args:
            bot: Discord 機器人實例
        """
        self.bot = bot
        # Logger is automatically set by LoggerMixin - no need to override
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

        # 建立主選單 Embed
        embed = discord.Embed(
            title="🤖 系統提示管理",
            description="歡迎使用統一系統提示管理介面！請選擇要執行的功能：",
            color=discord.Color.blue()
        )

        # 添加功能說明
        embed.add_field(
            name="🔧 主要功能",
            value=(
                "• **設定提示** - 設定頻道或伺服器系統提示\n"
                "• **查看配置** - 查看當前系統提示配置\n"
                "• **模組編輯** - 編輯特定 YAML 模組\n"
                "• **複製提示** - 複製系統提示到其他頻道\n"
                "• **移除提示** - 移除已設定的系統提示\n"
                "• **重置設定** - 重置系統提示配置"
            ),
            inline=False
        )

        embed.add_field(
            name="📋 使用說明",
            value=(
                "點擊下方按鈕來執行對應功能。\n"
                "系統支援三層繼承機制：YAML 基礎 → 伺服器預設 → 頻道特定"
            ),
            inline=False
        )

        embed.set_footer(text="提示：所有操作都會進行權限檢查，確保安全性")

        # 發送主選單
        await interaction.response.send_message(
            embed=embed,
            view=main_view,
            ephemeral=True
        )


async def setup(bot):
    """設定函式，用於載入 Cog"""
    await bot.add_cog(SystemPromptCommands(bot))