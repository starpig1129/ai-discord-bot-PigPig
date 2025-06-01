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

            reminder_time = self.parse_time(time_str, guild_id)
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
                duration=self.format_timedelta(time_diff, guild_id),
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

    def parse_time(self, time_str: str, guild_id: str = None) -> datetime:
        """解析時間字串，支援多語言格式"""
        current_time = datetime.now()
        
        # 多語言相對時間解析模式
        relative_patterns = [
            # 繁體中文
            (r'(\d+)(秒|分鐘|小時|天)後', {'秒': 'seconds', '分鐘': 'minutes', '小時': 'hours', '天': 'days'}),
            # 簡體中文
            (r'(\d+)(秒|分钟|小时|天)后', {'秒': 'seconds', '分钟': 'minutes', '小时': 'hours', '天': 'days'}),
            # 英文
            (r'(\d+)\s*(seconds?|minutes?|hours?|days?)\s*later', {
                'second': 'seconds', 'seconds': 'seconds',
                'minute': 'minutes', 'minutes': 'minutes',
                'hour': 'hours', 'hours': 'hours',
                'day': 'days', 'days': 'days'
            }),
            # 日文
            (r'(\d+)(秒|分|時間|日)後', {'秒': 'seconds', '分': 'minutes', '時間': 'hours', '日': 'days'})
        ]
        
        for pattern, unit_map in relative_patterns:
            time_match = re.match(pattern, time_str, re.IGNORECASE)
            if time_match:
                amount = int(time_match.group(1))
                unit_key = time_match.group(2).lower()
                unit = unit_map.get(unit_key)
                
                if unit == 'seconds':
                    return current_time + timedelta(seconds=amount)
                elif unit == 'minutes':
                    return current_time + timedelta(minutes=amount)
                elif unit == 'hours':
                    return current_time + timedelta(hours=amount)
                elif unit == 'days':
                    return current_time + timedelta(days=amount)
        
        # 絕對時間解析（支援多種格式）
        absolute_patterns = [
            '%Y年%m月%d日%H:%M:%S',  # 中文格式
            '%Y-%m-%d %H:%M:%S',     # 英文格式
            '%Y/%m/%d %H:%M:%S',     # 另一種英文格式
            '%Y年%m月%d日%H時%M分%S秒' # 完整中文格式
        ]
        
        for pattern in absolute_patterns:
            try:
                return datetime.strptime(time_str, pattern)
            except ValueError:
                continue

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
