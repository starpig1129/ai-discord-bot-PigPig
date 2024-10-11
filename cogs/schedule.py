import discord
from discord import app_commands
from discord.ext import commands
import yaml
from datetime import datetime, timedelta
import pytz
import os

class ScheduleManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.schedule_dir = "data/schedule"
        os.makedirs(self.schedule_dir, exist_ok=True)

    @app_commands.command(name="upload_schedule", description="上傳行程表YAML檔案")
    async def upload_schedule_command(self, interaction: discord.Interaction, file: discord.Attachment):
        await interaction.response.defer(thinking=True)
        try:
            await self.upload_schedule(interaction.user.id, file)
            await interaction.followup.send("行程表已成功上傳！")
        except Exception as e:
            await interaction.followup.send(f"上傳行程表時發生錯誤：{str(e)}")

    async def upload_schedule(self, user_id: int, file: discord.Attachment):
        async with self.bot.session.get(file.url) as response:
            yaml_data = await response.text()
        try:
            schedule = yaml.safe_load(yaml_data)
            with open(os.path.join(self.schedule_dir, f"{user_id}.yaml"), "w") as f:
                yaml.dump(schedule, f)
        except yaml.YAMLError as e:
            raise Exception(f"YAML檔案解析錯誤：{str(e)}")

    @app_commands.command(name="query_schedule", description="查詢行程表")
    @app_commands.describe(
        query_type="查詢類型 (full, specific_time, next)",
        time="指定時間 (YYYY-MM-DD HH:MM:SS, only for specific_time)"
    )
    async def query_schedule_command(self, interaction: discord.Interaction, query_type: str, time: str = None):
        await interaction.response.defer(thinking=True)
        try:
            result = await self.query_schedule(interaction.user.id, query_type, time)
            await interaction.followup.send(result)
        except Exception as e:
            await interaction.followup.send(f"查詢行程表時發生錯誤：{str(e)}")

    @commands.command(name="query_schedule", description="查詢行程表")
    async def query_schedule_general(self, ctx: commands.Context, query_type: str, time: str = None):
        try:
            result = await self.query_schedule(ctx.author.id, query_type, time)
            await ctx.send(result)
        except Exception as e:
            await ctx.send(f"查詢行程表時發生錯誤：{str(e)}")


    async def query_schedule(self, user_id: int, query_type: str, time: str = None):
        filepath = os.path.join(self.schedule_dir, f"{user_id}.yaml")
        if not os.path.exists(filepath):
            return "找不到您的行程表。請使用 `/upload_schedule` 命令上傳行程表。"
        with open(filepath, "r") as f:
            schedule = yaml.safe_load(f)

        tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tz)

        if query_type == "full":
            return self.format_full_schedule(schedule)
        elif query_type == "specific_time":
            try:
                specific_time = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
                return self.format_specific_time_schedule(schedule, specific_time)
            except ValueError:
                return "無效的時間格式。請使用 YYYY-MM-DD HH:MM:SS 格式。"
        elif query_type == "next":
            return self.format_next_schedule(schedule, now)
        else:
            return "無效的查詢類型。"

    def format_full_schedule(self, schedule):
        output = "**完整行程表:**\n"
        if not schedule:
            return "行程表是空的。"
        for date, events in schedule.items():
            output += f"**{date}:**\n"
            if events:
                output += "| 時間 | 說明 |\n"
                output += "|---|---| \n"
                for event in events:
                    output += f"| {event['time']} | {event['description']} |\n"
            else:
                output += "沒有行程。\n"
        return output

    def format_specific_time_schedule(self, schedule, specific_time):
        output = f"**{specific_time.strftime('%Y-%m-%d %H:%M:%S')} 的行程:**\n"
        found = False
        for date, events in schedule.items():
            for event in events:
                event_time = datetime.strptime(event['time'], "%H:%M:%S").replace(year=specific_time.year, month=specific_time.month, day=specific_time.day)
                if event_time == specific_time:
                    output += f"- {event['time']}: {event['description']}\n"
                    found = True
        return output if found else "沒有找到該時間的行程。"

    def format_next_schedule(self, schedule, now):
        next_event = None
        for date, events in schedule.items():
            for event in events:
                event_time = datetime.strptime(event['time'], "%H:%M:%S").replace(year=now.year, month=now.month, day=now.day)
                if event_time > now:
                    if next_event is None or event_time < next_event[0]:
                        next_event = (event_time, event['description'])
        if next_event:
            return f"下一個行程：{next_event[0].strftime('%H:%M:%S')} - {next_event[1]}"
        else:
            return "沒有找到下一個行程。"


async def setup(bot):
    await bot.add_cog(ScheduleManager(bot))
