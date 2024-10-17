import discord
from discord.ext import commands
from discord import app_commands
import json
import os

class ChannelManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = "data/channel_configs"
        os.makedirs(self.data_dir, exist_ok=True)

    def get_config_path(self, guild_id):
        return os.path.join(self.data_dir, f"{guild_id}.json")

    def load_config(self, guild_id):
        config_path = self.get_config_path(guild_id)
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)
        else:
            return {"mode": "unrestricted", "whitelist": [], "blacklist": []}

    def save_config(self, guild_id, config):
        config_path = self.get_config_path(guild_id)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

    async def cog_check(self, interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator

    @app_commands.command(name="set_channel_mode", description="設定頻道回應模式")
    @app_commands.choices(mode=[
        app_commands.Choice(name="無限制", value="unrestricted"),
        app_commands.Choice(name="白名單", value="whitelist"),
        app_commands.Choice(name="黑名單", value="blacklist")
    ])
    async def set_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        config["mode"] = mode.value
        self.save_config(guild_id, config)
        await interaction.response.send_message(f"已將頻道回應模式設定為：{mode.name}")

    @app_commands.command(name="add_channel", description="新增頻道到白名單或黑名單")
    @app_commands.choices(list_type=[
        app_commands.Choice(name="白名單", value="whitelist"),
        app_commands.Choice(name="黑名單", value="blacklist")
    ])
    async def add_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel, list_type: app_commands.Choice[str]):
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        if channel_id not in config[list_type.value]:
            config[list_type.value].append(channel_id)
            self.save_config(guild_id, config)
            await interaction.response.send_message(f"已將頻道 <#{channel_id}> 新增到 {list_type.name}")
        else:
            await interaction.response.send_message(f"頻道 <#{channel_id}> 已存在於 {list_type.name}")

    @app_commands.command(name="remove_channel", description="移除頻道從白名單或黑名單")
    @app_commands.choices(list_type=[
        app_commands.Choice(name="白名單", value="whitelist"),
        app_commands.Choice(name="黑名單", value="blacklist")
    ])
    async def remove_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel, list_type: app_commands.Choice[str]):
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        if channel_id in config[list_type.value]:
            config[list_type.value].remove(channel_id)
            self.save_config(guild_id, config)
            await interaction.response.send_message(f"已將頻道 <#{channel_id}> 移除從 {list_type.name}")
        else:
            await interaction.response.send_message(f"頻道 <#{channel_id}> 不存在於 {list_type.name}")

    def is_allowed_channel(self, channel: discord.TextChannel, guild_id: str):
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        mode = config.get("mode", "unrestricted")

        if mode == "unrestricted":
            return True
        elif mode == "whitelist":
            return channel_id in config.get("whitelist", [])
        elif mode == "blacklist":
            return channel_id not in config.get("blacklist", [])
        return False

async def setup(bot):
    await bot.add_cog(ChannelManager(bot))
