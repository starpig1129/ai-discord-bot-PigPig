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
from datetime import datetime
import pytz
import json
import re

class SchoolScheduleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.weekday_map = {
            'Monday': '星期一', 'Tuesday': '星期二', 'Wednesday': '星期三',
            'Thursday': '星期四', 'Friday': '星期五', 'Saturday': '星期六', 'Sunday': '星期日'
        }

    @app_commands.command(name="TKUschedule", description="查詢課表")
    @app_commands.describe(
        query_type="查詢類型（next: 下一節課，now: 當前課程）",
        user="要查詢的用戶（可選，默認為自己）"
    )
    async def schedule_command(self, interaction: discord.Interaction, query_type: str = 'next', user: discord.User = None):
        await interaction.response.defer(thinking=True)
        result = await self.query_schedule(user or interaction.user, query_type)
        await interaction.followup.send(result)

    async def query_schedule(self, user: discord.User, query_type: str = 'next',message_to_edit: discord.Message = None) -> str:
        try:
            if message_to_edit :
                await message_to_edit.edit(content="看看課表")
            schedule = self.load_schedule_data(user.id)
            if schedule is None:
                return "找不到課表數據。"

            tz = pytz.timezone('Asia/Taipei')
            now = datetime.now(tz)
            current_hour = now.hour
            current_weekday = now.strftime('%A')
            current_class_period = current_hour - 7  # 8點開始為第1節
            current_weekday_cn = self.weekday_map.get(current_weekday, "")

            if query_type == 'next':
                return f'用戶 {user.name} 的課表：{self.find_next_class(schedule, current_weekday_cn, current_class_period)}'
            elif query_type == 'now':
                return f'用戶 {user.name} 的課表：{self.find_current_class(schedule, current_weekday_cn, current_class_period)}'
            else:
                return '無效的查詢類型'
        except Exception as e:
            return f'查詢課表時發生錯誤：{str(e)}'

    def load_schedule_data(self, user_id: int) -> dict:
        try:
            with open(f'./data/schedule_data/{user_id}.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def find_next_class(self, schedule: dict, weekday: str, current_class_period: int) -> str:
        if weekday not in schedule:
            return "今日無課程。"
        current_class_period = max(current_class_period, 0)
        for period in range(current_class_period, len(schedule[weekday])):
            if schedule[weekday][period]:
                class_info = schedule[weekday][period]
                return f"下一節課是第 {period + 1} 節 {period+8}:10開始，課名：{class_info['課名']}，教授：{class_info['教授']}，教室：{class_info['教室']}。"
        return "今日已無其他課程。"

    def find_current_class(self, schedule: dict, weekday: str, current_class_period: int) -> str:
        if weekday not in schedule:
            return "今日無課程。"
        if 0 <= current_class_period - 1 < len(schedule[weekday]) and schedule[weekday][current_class_period-1]:
            class_info = schedule[weekday][current_class_period-1]
            return f"目前是第 {current_class_period} 節，課名：{class_info['課名']}，教授：{class_info['教授']}，教室：{class_info['教室']}。"
        else:
            return "現在沒在上課。"

async def setup(bot):
    await bot.add_cog(SchoolScheduleCog(bot))