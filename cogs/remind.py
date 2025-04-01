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

from typing import Optional
from .language_manager import LanguageManager

class ReminderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    async def set_reminder(self, channel, target_user, time_str: str, message: str, message_to_edit: discord.Message = None, guild_id: str = None):
        try:
            if not self.lang_manager:
                self.lang_manager = LanguageManager.get_instance(self.bot)

            if message_to_edit:
                await message_to_edit.edit(content=self.lang_manager.translate(guild_id, "commands", "remind", "responses", "received"))

            reminder_time = self.parse_time(time_str)
            if reminder_time is None:
                return self.lang_manager.translate(guild_id, "commands", "remind", "responses", "invalid_format")

            time_diff = reminder_time - datetime.now()
            if time_diff.total_seconds() <= 0:
                return self.lang_manager.translate(guild_id, "commands", "remind", "responses", "future_time_required")

            # 準備確認消息
            confirm_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "remind", 
                "responses",
                "confirm_setup",
                duration=self.format_timedelta(time_diff),
                user=target_user.mention,
                message=message
            )
            
            if message_to_edit:
                await message_to_edit.edit(content = confirm_message)

            # 等待直到指定時間
            await asyncio.sleep(time_diff.total_seconds())
            
            # 發送實際的提醒消息
            reminder_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "remind",
                "responses",
                "reminder_message",
                user=target_user.mention,
                message=message
            )
            await channel.send(reminder_message)
            
            return self.lang_manager.translate(
                guild_id,
                "commands",
                "remind",
                "responses",
                "reminder_sent",
                user=target_user.mention
            )
        except Exception as e:
            return self.lang_manager.translate(
                guild_id,
                "commands",
                "remind",
                "responses",
                "error_setting",
                error=str(e)
            )

    @app_commands.command(name="remind", description="設置一個提醒")
    @app_commands.describe(
        time="提醒時間（例如：10分鐘後，或 2023年12月31日20:00:00）",
        message="提醒內容",
        user="要提醒的用戶（可選，默認為自己）"
    )
    async def remind(self, interaction: discord.Interaction, time: str, message: str, user: discord.User = None):
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild_id)
        target_user = user or interaction.user
        result = await self.set_reminder(
            interaction.channel,
            target_user,
            time,
            message,
            guild_id=guild_id
        )
        await interaction.followup.send(result, ephemeral=True)

    def parse_time(self, time_str: str) -> datetime:
        current_time = datetime.now()
        
        # 解析相對時間（例如：10分鐘後）
        time_match = re.match(r'(\d+)(秒|分鐘|小時|天)後', time_str)
        if time_match:
            amount = int(time_match.group(1))
            unit = time_match.group(2)
            if unit == '秒':
                return current_time + timedelta(seconds=amount)
            elif unit == '分鐘':
                return current_time + timedelta(minutes=amount)
            elif unit == '小時':
                return current_time + timedelta(hours=amount)
            elif unit == '天':
                return current_time + timedelta(days=amount)
        
        # 解析絕對時間（例如：2023年12月31日20:00:00）
        try:
            return datetime.strptime(time_str, '%Y年%m月%d日%H:%M:%S')
        except ValueError:
            pass

        return None

    def format_timedelta(self, td: timedelta) -> str:
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
