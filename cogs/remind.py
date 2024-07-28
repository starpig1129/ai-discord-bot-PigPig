import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import re

class ReminderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def set_reminder(self, channel, target_user, time_str: str, message: str, message_to_edit: discord.Message = None):
        try:
            if message_to_edit:
                await message_to_edit.edit(content = '收到提醒')
            reminder_time = self.parse_time(time_str)
            if reminder_time is None:
                return "無效的時間格式。請使用 '10分鐘後' 或 '2023年12月31日20:00:00' 格式。"
            time_diff = reminder_time - datetime.now()
            if time_diff.total_seconds() <= 0:
                return "提醒時間必須在將來。"

            # 準備確認消息
            confirm_message = f"已設置提醒：將在 {self.format_timedelta(time_diff)} 後提醒 {target_user.mention} {message}"
            
            if message_to_edit:
                await message_to_edit.edit(content = confirm_message)

            # 等待直到指定時間
            await asyncio.sleep(time_diff.total_seconds())
            
            # 發送實際的提醒消息
            await channel.send(f"{target_user.mention} 提醒：{message}")
            return f"提醒已發送給 {target_user.mention}"
        except Exception as e:
            return f"設置提醒時發生錯誤：{str(e)}"

    @app_commands.command(name="remind", description="設置一個提醒")
    @app_commands.describe(
        user="要提醒的用戶（可選，默認為自己）",
        time="提醒時間（例如：10分鐘後，或 2023年12月31日20:00:00）",
        message="提醒內容"
    )
    async def remind(self, interaction: discord.Interaction, time: str, message: str, user: discord.User = None):
        await interaction.response.defer(ephemeral=True)
        
        target_user = user or interaction.user
        result = await self.set_reminder(interaction.channel, target_user, time, message)
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