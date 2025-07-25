# MIT License

# Copyright (c) 2024 starpig1129

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import re
import dateparser

from typing import Optional
from .language_manager import LanguageManager

class ReminderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    async def _set_reminder_logic(self, channel, target_user, time_str: str, message: str, guild_id: str, interaction: Optional[discord.Interaction] = None):
        """核心提醒邏輯，可被斜線命令和LLM工具共用"""
        try:
            if not self.lang_manager:
                self.lang_manager = LanguageManager.get_instance(self.bot)

            # 如果是來自斜線命令，先發送一個 "已收到" 的臨時回覆
            if interaction:
                await interaction.followup.send(self.lang_manager.translate(guild_id, "commands", "remind", "responses", "received"), ephemeral=True)

            reminder_time = self.parse_time(time_str, guild_id)
            if reminder_time is None:
                error_msg = self.lang_manager.translate(guild_id, "commands", "remind", "responses", "invalid_format")
                if interaction:
                    await interaction.edit_original_response(content=error_msg)
                return error_msg

            time_diff = reminder_time - datetime.now()
            if time_diff.total_seconds() <= 0:
                error_msg = self.lang_manager.translate(guild_id, "commands", "remind", "responses", "future_time_required")
                if interaction:
                    await interaction.edit_original_response(content=error_msg)
                return error_msg

            # 準備確認消息
            confirm_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "remind",
                "responses",
                "confirm_setup",
                duration=self.format_timedelta(time_diff, guild_id),
                user=target_user.mention,
                message=message
            )
            
            if interaction:
                await interaction.edit_original_response(content=confirm_message)
            
            # 建立一個背景任務來處理等待和發送
            async def reminder_task():
                await asyncio.sleep(time_diff.total_seconds())
                reminder_message_content = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "remind",
                    "responses",
                    "reminder_message",
                    user=target_user.mention,
                    message=message
                )
                await channel.send(reminder_message_content)

            asyncio.create_task(reminder_task())
            
            return confirm_message

        except Exception as e:
            error_msg = self.lang_manager.translate(
                guild_id,
                "commands",
                "remind",
                "responses",
                "error_setting",
                error=str(e)
            )
            if interaction:
                await interaction.edit_original_response(content=error_msg)
            return error_msg

    @app_commands.command(name="remind", description="設置一個提醒")
    @app_commands.describe(
        time="提醒時間（例如：10分鐘後，或 2023年12月31日20:00:00）",
        message="提醒內容",
        user="要提醒的用戶（可選，默認為自己）"
    )
    async def remind(self, interaction: discord.Interaction, time: str, message: str, user: discord.User = None):
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild_id)
        target_user = user or interaction.user
        
        # 呼叫核心邏輯
        await self._set_reminder_logic(
            channel=interaction.channel,
            target_user=target_user,
            time_str=time,
            message=message,
            guild_id=guild_id,
            interaction=interaction
        )

    def parse_time(self, time_str: str, guild_id: str = None) -> Optional[datetime]:
        """
        使用 dateparser 解析時間字串，支援多種自然語言格式。
        例如: "15 minutes from now", "in 2 hours", "2023-12-31 20:00"
        """
        try:
            # PREFER_DATES_FROM: 'future' 確保相對時間 (例如 "in 15 minutes") 被解析為未來時間
            # RETURN_AS_TIMEZONE_AWARE: False 讓其返回 naive datetime, 與專案其他部分保持一致
            parsed_time = dateparser.parse(
                time_str,
                settings={'PREFER_DATES_FROM': 'future', 'RETURN_AS_TIMEZONE_AWARE': False}
            )
            return parsed_time
        except Exception:
            # 如果 dateparser 發生任何錯誤，返回 None
            return None

    def format_timedelta(self, td: timedelta, guild_id: str = None) -> str:
        """格式化時間長度為本地化字串"""
        if not self.lang_manager:
            # 備用機制
            return self._format_time_fallback(td)
        
        total_seconds = int(td.total_seconds())
        
        # 計算各個時間單位
        years, remainder = divmod(total_seconds, 365 * 24 * 3600)
        months, remainder = divmod(remainder, 30 * 24 * 3600)
        weeks, remainder = divmod(remainder, 7 * 24 * 3600)
        days, remainder = divmod(remainder, 24 * 3600)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # 建立本地化時間格式
        parts = []
        time_components = [
            (years, "years"),
            (months, "months"),
            (weeks, "weeks"),
            (days, "days"),
            (hours, "hours"),
            (minutes, "minutes"),
            (seconds, "seconds")
        ]
        
        for value, unit_key in time_components:
            if value > 0:
                unit_text = self.lang_manager.translate(
                    guild_id, "commands", "remind", "time_units", unit_key
                )
                if unit_text:
                    parts.append(f"{value}{unit_text}")
        
        # 如果沒有任何時間單位，顯示0秒
        if not parts:
            unit_text = self.lang_manager.translate(
                guild_id, "commands", "remind", "time_units", "seconds"
            )
            parts.append(f"0{unit_text or '秒'}")
        
        return " ".join(parts)
    
    def _format_time_fallback(self, td: timedelta) -> str:
        """備用時間格式化機制（當翻譯系統不可用時）"""
        days, remainder = divmod(td.total_seconds(), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{int(days)}天")
        if hours > 0:
            parts.append(f"{int(hours)}小時")
        if minutes > 0:
            parts.append(f"{int(minutes)}分鐘")
        if seconds > 0 or not parts:
            parts.append(f"{int(seconds)}秒")
        
        return " ".join(parts)

async def setup(bot):
    await bot.add_cog(ReminderCog(bot))
