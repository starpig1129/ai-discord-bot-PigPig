import discord
from discord import app_commands
from discord.ext import commands
import yaml
from datetime import datetime
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
            await self.upload_schedule(interaction.user.id, interaction.channel_id, file)
            await interaction.followup.send("行程表已成功上傳！")
        except Exception as e:
            await interaction.followup.send(f"上傳行程表時發生錯誤：{str(e)}")

    async def upload_schedule(self, user_id: int, channel_id: int, file: discord.Attachment):
        async with self.bot.session.get(file.url) as response:
            yaml_data = await response.text()
        try:
            schedule = yaml.safe_load(yaml_data)
            schedule_data = {"channel_id": channel_id, "schedule": schedule}
            with open(os.path.join(self.schedule_dir, f"{user_id}.yaml"), "w") as f:
                yaml.dump(schedule_data, f)
        except yaml.YAMLError as e:
            raise Exception(f"YAML檔案解析錯誤：{str(e)}")

    @app_commands.command(name="query_schedule", description="查詢行程表")
    @app_commands.choices(query_type=[
        app_commands.Choice(name="完整行程表", value="full"),
        app_commands.Choice(name="特定時間", value="specific_time"),
        app_commands.Choice(name="下一個行程", value="next")
    ])
    @app_commands.choices(day=[
        app_commands.Choice(name="星期一", value="Monday"),
        app_commands.Choice(name="星期二", value="Tuesday"),
        app_commands.Choice(name="星期三", value="Wednesday"),
        app_commands.Choice(name="星期四", value="Thursday"),
        app_commands.Choice(name="星期五", value="Friday"),
        app_commands.Choice(name="星期六", value="Saturday"),
        app_commands.Choice(name="星期日", value="Sunday")
    ])
    async def query_schedule_command(self, interaction: discord.Interaction, query_type: app_commands.Choice[str], time: str = None, day: app_commands.Choice[str] = None, target_user: discord.Member = None):
        await interaction.response.defer(thinking=True)
        try:
            target_user_id = target_user.id if target_user else interaction.user.id
            result = await self.query_schedule(interaction, query_type.value, time, day.value if day else None, target_user_id)
            await interaction.followup.send(result)
        except Exception as e:
            await interaction.followup.send(f"查詢行程表時發生錯誤：{str(e)}")

    async def query_schedule(self, interaction_or_ctx, query_type: str, time: str = None, day: str = None, target_user_id:int = None):
        try:
            user_id = interaction_or_ctx.user.id if hasattr(interaction_or_ctx, 'user') else interaction_or_ctx.author.id
            channel_id = interaction_or_ctx.channel_id if hasattr(interaction_or_ctx, 'channel_id') else interaction_or_ctx.channel.id
        except AttributeError:
            return "Invalid interaction or context object."

        filepath = os.path.join(self.schedule_dir, f"{target_user_id}.yaml")
        if not os.path.exists(filepath):
            return "找不到您的行程表。請使用 `/upload_schedule` 命令上傳行程表。"
        with open(filepath, "r") as f:
            schedule_data = yaml.safe_load(f)

        guild = interaction_or_ctx.guild
        queried_user = await guild.fetch_member(target_user_id)
        if queried_user is None:
            return "找不到該使用者。"

        query_channel = guild.get_channel(channel_id)
        schedule_channel = guild.get_channel(schedule_data["channel_id"])

        if query_channel is None or schedule_channel is None:
            return "找不到頻道。"

        query_perms = query_channel.permissions_for(interaction_or_ctx.user)
        schedule_perms = schedule_channel.permissions_for(queried_user)

        if not query_perms.read_messages or not schedule_perms.read_messages:
            return "您或被查詢者無權限查看此頻道。"


        schedule = schedule_data["schedule"]
        tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tz)

        if query_type == "full":
            return self.format_full_schedule(schedule)
        elif query_type == "specific_time":
            try:
                specific_time = datetime.strptime(time if time else now.strftime("%Y-%m-%d %H:%M:%S"), "%Y-%m-%d %H:%M:%S")
                return self.format_specific_time_schedule(schedule, specific_time, day)
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
        for day, events in schedule.items():
            output += f"**{day}:**\n"
            if events:
                output += "| 時間 | 說明 |\n"
                output += "|---|---| \n"
                for event in events:
                    output += f"| {event['time']} | {event['description']} |\n"
            else:
                output += "沒有行程。\n"
        return output

    def format_specific_time_schedule(self, schedule, specific_time, day):
        output = f"**{specific_time.strftime('%Y-%m-%d %H:%M:%S')} 的行程:**\n"
        found = False
        if day and day in schedule:
            for event in schedule[day]:
                try:
                    event_time = datetime.strptime(event['time'], "%H:%M-%H:%M").replace(year=specific_time.year, month=specific_time.month, day=specific_time.day)
                    if event_time == specific_time:
                        output += f"- {event['time']}: {event['description']}\n"
                        found = True
                except ValueError:
                    pass
        elif not day:
            current_day = specific_time.strftime("%A")
            if current_day in schedule:
                for event in schedule[current_day]:
                    try:
                        event_time = datetime.strptime(event['time'], "%H:%M-%H:%M").replace(year=specific_time.year, month=specific_time.month, day=specific_time.day)
                        if event_time == specific_time:
                            output += f"- {event['time']}: {event['description']}\n"
                            found = True
                    except ValueError:
                        pass

        return output if found else "沒有找到該時間的行程。"

    def format_next_schedule(self, schedule, now):
        next_event = None
        for day, events in schedule.items():
            for event in events:
                try:
                    event_time_str = event['time']
                    start_time, end_time = event_time_str.split('-')
                    start_time = datetime.strptime(start_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
                    end_time = datetime.strptime(end_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
                    if start_time > now:
                        if next_event is None or start_time < next_event[0]:
                            next_event = (start_time, event['description'])
                except ValueError:
                    pass
        if next_event:
            return f"下一個行程：{next_event[0].strftime('%H:%M')} - {next_event[1]}"
        else:
            return "沒有找到下一個行程。"

    @app_commands.command(name="update_schedule", description="更新或創建行程表")
    async def update_schedule_command(self, interaction: discord.Interaction, day: str, time: str, description: str):
        await interaction.response.defer(thinking=True)
        try:
            await self.update_schedule(interaction.user.id, day, time, description)
            await interaction.followup.send("行程表已成功更新或創建！")
        except Exception as e:
            await interaction.followup.send(f"更新或創建行程表時發生錯誤：{str(e)}")

    async def update_schedule(self, user_id: int, day: str, time: str, description: str):
        filepath = os.path.join(self.schedule_dir, f"{user_id}.yaml")
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                yaml.dump({"channel_id": 0, "schedule": {}}, f)

        with open(filepath, "r") as f:
            schedule_data = yaml.safe_load(f)
        schedule = schedule_data["schedule"]

        if day not in schedule:
            schedule[day] = []
        schedule[day].append({"time": time, "description": description})

        schedule_data["schedule"] = schedule
        with open(filepath, "w") as f:
            yaml.dump(schedule_data, f)

    @app_commands.command(name="show_template", description="顯示行程表範本")
    async def show_template_command(self, interaction: discord.Interaction):
        with open(os.path.join(self.schedule_dir, "template.yaml"), "r") as f:
            template = f.read()
        await interaction.response.send_message(f"```yaml\n{template}\n```")


async def setup(bot):
    await bot.add_cog(ScheduleManager(bot))
