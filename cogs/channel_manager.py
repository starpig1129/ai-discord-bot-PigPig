import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import time
from addons.logging import get_logger
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from .language_manager import LanguageManager
from addons.tokens import tokens
from function import func
import asyncio

# Module-level logger. Use "Bot" as default server_id for module-level events.
log = get_logger(server_id="Bot", source=__name__)

class ChannelManager(commands.Cog):
    """Cog for managing server-wide and channel-specific response modes and permissions."""

    def __init__(self, bot):
        self.bot = bot
        self.data_dir = "data/channel_configs"
        self.lang_manager: Optional[LanguageManager] = None
        self.tokens = tokens
        os.makedirs(self.data_dir, exist_ok=True)

    async def cog_load(self):
        """Initialize LanguageManager when the cog is loaded."""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    def get_config_path(self, guild_id: str) -> str:
        """Get the file path for a guild's configuration."""
        return os.path.join(self.data_dir, f"{guild_id}.json")

    def load_config(self, guild_id: str) -> Dict[str, Any]:
        """Load configuration for a specific guild."""
        config_path = self.get_config_path(guild_id)
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                # Ensure necessary keys exist
                if "auto_response" not in config:
                    config["auto_response"] = {}
                if "channel_modes" not in config:
                    config["channel_modes"] = {}
                if "mode" not in config:
                    config["mode"] = "unrestricted"
                return config
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._get_default_config()
        else:
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Provide a default configuration template."""
        return {
            "mode": "unrestricted", # Server-wide mode
            "whitelist": [],
            "blacklist": [],
            "auto_response": {},
            "channel_modes": {} # Per-channel mode overrides
        }

    def save_config(self, guild_id: str, config: Dict[str, Any]):
        """Save configuration for a specific guild."""
        config_path = self.get_config_path(guild_id)
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"saving config for guild {guild_id}"))

    async def check_admin_permissions(self, interaction: discord.Interaction, *, defer: bool = False) -> bool:
        """Check if the user has administrator permissions or is the bot owner."""
        if defer and not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        
        bot_owner_id = getattr(self.tokens, 'bot_owner_id', 0)
        if interaction.user.guild_permissions.administrator or interaction.user.id == bot_owner_id:
            return True
        
        if self.lang_manager:
            error_message = self.lang_manager.translate(
                str(interaction.guild_id),
                "errors",
                "permission_denied"
            )
        else:
            error_message = "You do not have permission to perform this action. Restricted to administrators."
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=error_message)
        else:
            await interaction.response.send_message(error_message, ephemeral=True)
        return False

    @app_commands.command(name="set_server_mode", description="Set the server-wide response mode (Whitelist/Blacklist)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Unrestricted", value="unrestricted"),
        app_commands.Choice(name="Whitelist", value="whitelist"),
        app_commands.Choice(name="Blacklist", value="blacklist")
    ])
    async def set_server_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        """Set the global response mode for the entire server."""
        if not await self.check_admin_permissions(interaction, defer=True):
            return
            
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        config["mode"] = mode.value
        self.save_config(guild_id, config)
        
        if self.lang_manager:
            mode_name = self.lang_manager.translate(
                guild_id, "commands", "channel_manager", "set_server_mode", "choices", mode.value
            )
            response = self.lang_manager.translate(
                guild_id, "commands", "channel_manager", "set_server_mode", "responses", "success", mode=mode_name
            )
        else:
            response = f"Set **Server-wide** response mode to: {mode.name}"

        await interaction.edit_original_response(content=response)

    @app_commands.command(name="set_channel_mode", description="Set a special mode for a specific channel (e.g., Story Mode)")
    @app_commands.describe(channel="The channel to set", mode="The mode to set for this channel")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Default (Follow Server Settings)", value="default"),
        app_commands.Choice(name="Story Mode", value="story")
    ])
    async def set_channel_mode(self, interaction: discord.Interaction, channel: discord.TextChannel, mode: app_commands.Choice[str]):
        """Configure a specific mode override for a single channel."""
        if not await self.check_admin_permissions(interaction, defer=True):
            return

        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        channel_id = str(channel.id)

        if mode.value == "default":
            if channel_id in config["channel_modes"]:
                del config["channel_modes"][channel_id]
                if self.lang_manager:
                    message = self.lang_manager.translate(
                        guild_id, "commands", "channel_manager", "set_channel_mode", "responses", "reset", channel=channel.mention
                    )
                else:
                    message = f"Reset mode for {channel.mention} to default."
            else:
                if self.lang_manager:
                    message = self.lang_manager.translate(
                        guild_id, "commands", "channel_manager", "set_channel_mode", "responses", "already_default", channel=channel.mention
                    )
                else:
                    message = f"{channel.mention} is already using default mode."
        else:
            config["channel_modes"][channel_id] = mode.value
            if self.lang_manager:
                mode_name = self.lang_manager.translate(
                    guild_id, "commands", "channel_manager", "set_channel_mode", "choices", mode.value
                )
                message = self.lang_manager.translate(
                    guild_id, "commands", "channel_manager", "set_channel_mode", "responses", "success", channel=channel.mention, mode=mode_name
                )
            else:
                message = f"Set mode for {channel.mention} to: **{mode.name}**."

        self.save_config(guild_id, config)
        await interaction.edit_original_response(content=message)

    @app_commands.command(name="add_channel", description="Add channel to whitelist or blacklist")
    @app_commands.choices(list_type=[
        app_commands.Choice(name="Whitelist", value="whitelist"),
        app_commands.Choice(name="Blacklist", value="blacklist")
    ])
    async def add_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel, list_type: app_commands.Choice[str]):
        """Add a channel to the server's whitelist or blacklist."""
        if not await self.check_admin_permissions(interaction, defer=True):
            return
            
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        
        if self.lang_manager:
            list_type_name = self.lang_manager.translate(
                guild_id, "commands", "channel_manager", "add_channel", "choices", list_type.value
            )
        else:
            list_type_name = list_type.name
        
        if channel_id not in config[list_type.value]:
            config[list_type.value].append(channel_id)
            self.save_config(guild_id, config)
            
            if self.lang_manager:
                success_message = self.lang_manager.translate(
                    guild_id, "commands", "channel_manager", "add_channel", "responses", "success", channel=f"<#{channel_id}>", list_type=list_type_name
                )
            else:
                success_message = f"Added <#{channel_id}> to {list_type_name}"
            
            await interaction.edit_original_response(content=success_message)
        else:
            if self.lang_manager:
                exists_message = self.lang_manager.translate(
                    guild_id, "commands", "channel_manager", "add_channel", "responses", "already_exists", channel=f"<#{channel_id}>", list_type=list_type_name
                )
            else:
                exists_message = f"<#{channel_id}> already exists in {list_type_name}"
            
            await interaction.edit_original_response(content=exists_message)

    @app_commands.command(name="remove_channel", description="Remove channel from whitelist or blacklist")
    @app_commands.choices(list_type=[
        app_commands.Choice(name="Whitelist", value="whitelist"),
        app_commands.Choice(name="Blacklist", value="blacklist")
    ])
    async def remove_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel, list_type: app_commands.Choice[str]):
        """Remove a channel from the server's whitelist or blacklist."""
        if not await self.check_admin_permissions(interaction, defer=True):
            return
            
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        
        if self.lang_manager:
            list_type_name = self.lang_manager.translate(
                guild_id, "commands", "channel_manager", "remove_channel", "choices", list_type.value
            )
        else:
            list_type_name = list_type.name
        
        if channel_id in config[list_type.value]:
            config[list_type.value].remove(channel_id)
            self.save_config(guild_id, config)
            
            if self.lang_manager:
                success_message = self.lang_manager.translate(
                    guild_id, "commands", "channel_manager", "remove_channel", "responses", "success", channel=f"<#{channel_id}>", list_type=list_type_name
                )
            else:
                success_message = f"Removed <#{channel_id}> from {list_type_name}"
            
            await interaction.edit_original_response(content=success_message)
        else:
            if self.lang_manager:
                not_found_message = self.lang_manager.translate(
                    guild_id, "commands", "channel_manager", "remove_channel", "responses", "not_found", channel=f"<#{channel_id}>", list_type=list_type_name
                )
            else:
                not_found_message = f"<#{channel_id}> does not exist in {list_type_name}"
            
            await interaction.edit_original_response(content=not_found_message)

    @app_commands.command(name="auto_response", description="Set channel auto-response")
    async def auto_response_command(self, interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool):
        """Enable or disable automatic bot responses in a specific channel."""
        if not await self.check_admin_permissions(interaction, defer=True):
            return
            
        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        config["auto_response"][channel_id] = enabled
        self.save_config(guild_id, config)
        
        if self.lang_manager:
            success_message = self.lang_manager.translate(
                guild_id, "commands", "channel_manager", "auto_response", "responses", "success", channel=f"<#{channel_id}>", enabled=str(enabled)
            )
        else:
            success_message = f"Set auto-response for <#{channel_id}> to: {enabled}"
        
        await interaction.edit_original_response(content=success_message)


    @app_commands.command(name="channel_status", description="View the current channel configuration and response modes")
    async def channel_status(self, interaction: discord.Interaction):
        """Display the current channel management configuration."""
        if not await self.check_admin_permissions(interaction, defer=True):
            return

        guild_id = str(interaction.guild_id)
        config = self.load_config(guild_id)

        server_mode = config.get("mode", "unrestricted")
        whitelist = [f"<#{cid}>" for cid in config.get("whitelist", [])]
        blacklist = [f"<#{cid}>" for cid in config.get("blacklist", [])]

        channel_modes = config.get("channel_modes", {})
        modes_str = "\n".join([f"<#{cid}>: {mode}" for cid, mode in channel_modes.items()]) if channel_modes else "None"

        auto_responses = config.get("auto_response", {})
        auto_resp_str = "\n".join([f"<#{cid}>: {'Enabled' if enabled else 'Disabled'}" for cid, enabled in auto_responses.items() if enabled]) if any(auto_responses.values()) else "None"

        embed = discord.Embed(title="Channel Management Status", color=discord.Color.blue())
        embed.add_field(name="Server Mode", value=server_mode.capitalize(), inline=False)

        if whitelist:
            embed.add_field(name="Whitelist", value=", ".join(whitelist), inline=False)
        if blacklist:
            embed.add_field(name="Blacklist", value=", ".join(blacklist), inline=False)

        embed.add_field(name="Channel Specific Modes", value=modes_str, inline=False)
        embed.add_field(name="Auto Responses", value=auto_resp_str, inline=False)

        await interaction.edit_original_response(content=None, embed=embed)

    def is_allowed_channel(self, channel: discord.TextChannel, guild_id: str) -> Tuple[bool, bool, Optional[str]]:
        """
        Determine if the bot is allowed to respond in a channel and get its effective mode.

        Returns:
            A tuple of (is_allowed, auto_response_enabled, effective_mode).
        """
        config = self.load_config(guild_id)
        channel_id = str(channel.id)
        auto_response_enabled = config.get("auto_response", {}).get(channel_id, False)

        # 1. Check for a channel-specific mode override
        channel_mode = config.get("channel_modes", {}).get(channel_id)
        if channel_mode: # e.g., 'story'
            return True, auto_response_enabled, channel_mode

        # 2. If no override, use the server-wide mode
        server_mode = config.get("mode", "unrestricted")
        if server_mode == "unrestricted":
            return True, auto_response_enabled, server_mode
        elif server_mode == "whitelist":
            is_allowed = channel_id in config.get("whitelist", [])
            return is_allowed, auto_response_enabled, server_mode
        elif server_mode == "blacklist":
            is_allowed = channel_id not in config.get("blacklist", [])
            return is_allowed, auto_response_enabled, server_mode
            
        return False, False, server_mode


async def setup(bot):
    """Set up the ChannelManager cog."""
    await bot.add_cog(ChannelManager(bot))
