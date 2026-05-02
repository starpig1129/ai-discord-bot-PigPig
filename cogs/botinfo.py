import discord
from discord.ext import commands
from discord import app_commands
import platform
from datetime import datetime
from typing import Optional
from addons.logging import get_logger

# Module-level logger. Use "Bot" as default server_id for module-level events.
log = get_logger(server_id="Bot", source=__name__)

from .language_manager import LanguageManager
from function import func


class BotInfo(commands.Cog):
    """Cog for displaying bot information and system statistics."""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.utcnow()
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """Initialize LanguageManager when the cog is loaded."""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    def _format_uptime(self, uptime, guild_id: str = "0"):
        """Format uptime duration into a localized human-readable string."""
        days, remainder = divmod(int(uptime.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Localized units
        if self.lang_manager:
            d_unit = self.lang_manager.translate(guild_id, "commands", "botinfo", "uptime_units", "days")
            h_unit = self.lang_manager.translate(guild_id, "commands", "botinfo", "uptime_units", "hours")
            m_unit = self.lang_manager.translate(guild_id, "commands", "botinfo", "uptime_units", "minutes")
            s_unit = self.lang_manager.translate(guild_id, "commands", "botinfo", "uptime_units", "seconds")
        else:
            d_unit, h_unit, m_unit, s_unit = "d", "h", "m", "s"

        parts = []
        if days:
            parts.append(f"{days}{d_unit}")
        if hours:
            parts.append(f"{hours}{h_unit}")
        if minutes:
            parts.append(f"{minutes}{m_unit}")
        if seconds or not parts:
            parts.append(f"{seconds}{s_unit}")

        return " ".join(parts)

    @app_commands.command(name="botinfo", description="Show detailed bot information")
    async def botinfo(self, interaction: discord.Interaction):
        """Display comprehensive bot information and performance metrics."""
        # Localize command description
        if self.lang_manager:
            guild_id = str(interaction.guild_id) if interaction.guild_id else "0"
            localized_desc = self.lang_manager.translate(guild_id, "commands", "botinfo", "description")
            if localized_desc and localized_desc != "botinfo":
                self.botinfo.description = localized_desc

        try:
            await interaction.response.defer()

            bot = interaction.client
            guild_id = str(interaction.guild_id) if interaction.guild_id else "0"

            # Calculate uptime
            uptime = datetime.utcnow() - self.start_time
            uptime_str = self._format_uptime(uptime, guild_id)

            # Network latency
            latency = round(bot.latency * 1000, 2)

            # System information
            try:
                import resource
                memory_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KB to MB on Linux
                if platform.system() == "Windows":
                    memory_usage = memory_usage * 1024  # KB on Windows
            except:
                memory_usage = "N/A"

            # Check if LanguageManager is available
            if not self.lang_manager:
                # Fallback values if LanguageManager is unavailable
                title = "Bot Information Overview"
                basic_stats_name = "Basic Statistics"
                servers_label = "Servers"
                users_label = "Users"
                text_channels_label = "Text Channels"
                voice_channels_label = "Voice Channels"
                loaded_cogs_label = "Loaded Cogs"
                performance_name = "Performance Monitoring"
                latency_label = "Latency"
                memory_usage_label = "Memory Usage"
                uptime_label = "Uptime"
                cogs_name = "Feature Modules"
                commands_label = "commands"
                no_cogs_label = "No loaded modules"
                status_online = "Online"
                status_idle = "Idle"
                status_dnd = "Do Not Disturb"
                status_offline = "Offline"
                status_unknown = "Unknown"
            else:
                title = self.lang_manager.translate(guild_id, "commands", "botinfo", "title")
                basic_stats_name = self.lang_manager.translate(guild_id, "commands", "botinfo", "fields", "basic_stats", "name")
                servers_label = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'fields', 'basic_stats', 'servers')
                users_label = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'fields', 'basic_stats', 'users')
                text_channels_label = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'fields', 'basic_stats', 'text_channels')
                voice_channels_label = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'fields', 'basic_stats', 'voice_channels')
                loaded_cogs_label = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'fields', 'basic_stats', 'loaded_cogs')
                performance_name = self.lang_manager.translate(guild_id, "commands", "botinfo", "fields", "performance", "name")
                latency_label = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'fields', 'performance', 'latency')
                memory_usage_label = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'fields', 'performance', 'memory_usage')
                uptime_label = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'fields', 'performance', 'uptime')
                cogs_name = self.lang_manager.translate(guild_id, "commands", "botinfo", "fields", "cogs", "name")
                commands_label = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'fields', 'cogs', 'commands')
                no_cogs_label = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'fields', 'cogs', 'no_cogs')
                status_online = self.lang_manager.translate(guild_id, "commands", "botinfo", "status", "online")
                status_idle = self.lang_manager.translate(guild_id, "commands", "botinfo", "status", "idle")
                status_dnd = self.lang_manager.translate(guild_id, "commands", "botinfo", "status", "dnd")
                status_offline = self.lang_manager.translate(guild_id, "commands", "botinfo", "status", "offline")
                status_unknown = self.lang_manager.translate(guild_id, 'commands', 'botinfo', 'status', 'unknown')

            # Main Embed
            main_embed = discord.Embed(
                title=title,
                color=discord.Color.from_rgb(114, 137, 218),
                timestamp=datetime.utcnow()
            )

            # Securely get user info
            user_name = getattr(bot.user, 'name', 'Unknown')
            discriminator = getattr(bot.user, 'discriminator', '0000')
            avatar_url = getattr(bot.user, 'display_avatar', getattr(bot.user, 'avatar', None))
            if avatar_url:
                avatar_url = avatar_url.url if hasattr(avatar_url, 'url') else str(avatar_url)

            main_embed.set_thumbnail(url=avatar_url)
            main_embed.set_author(name=f"{user_name}#{discriminator}", icon_url=avatar_url)

            # Basic Statistics
            main_embed.add_field(
                name=basic_stats_name,
                value="```yml\n"
                    f"{servers_label}: {len(getattr(bot, 'guilds', [])):,}\n"
                    f"{users_label}: {sum(getattr(g, 'member_count', 0) for g in getattr(bot, 'guilds', [])):,}\n"
                    f"{text_channels_label}: {len([c for c in bot.get_all_channels() if isinstance(c, discord.TextChannel)]):,}\n"
                    f"{voice_channels_label}: {len([c for c in bot.get_all_channels() if isinstance(c, discord.VoiceChannel)]):,}\n"
                    f"{loaded_cogs_label}: {len(getattr(bot, 'cogs', {})):,}\n"
                    "```",
                inline=False
            )

            # Performance Monitoring
            memory_str = f"{memory_usage:.1f}MB" if isinstance(memory_usage, (int, float)) else str(memory_usage)
            main_embed.add_field(
                name=performance_name,
                value="```yml\n"
                    f"{latency_label}: {latency}ms\n"
                    f"{memory_usage_label}: {memory_str}\n"
                    f"{uptime_label}: {uptime_str}\n"
                    "```",
                inline=False
            )

            # Feature Modules
            cog_list = []
            for cog_name, cog in getattr(bot, 'cogs', {}).items():
                command_count = len([c for c in cog.get_commands()] + [c for c in cog.get_app_commands()])
                if command_count > 0:
                    cog_list.append(f"{cog_name}: {command_count} {commands_label}")

            main_embed.add_field(
                name=cogs_name,
                value="```\n" + "\n".join(cog_list[:8]) + "\n```" if cog_list else f"```\n{no_cogs_label}\n```",
                inline=False
            )

            # Status Indicators
            status_indicators = {
                discord.Status.online: status_online,
                discord.Status.idle: status_idle,
                discord.Status.dnd: status_dnd,
                discord.Status.offline: status_offline
            }

            bot_status = getattr(bot, 'status', discord.Status.offline)
            status_text = status_indicators.get(bot_status, status_unknown)
            status_prefix = self.lang_manager.translate(guild_id, "commands", "botinfo", "footer", "status_prefix") if self.lang_manager else "Status: "
            main_embed.set_footer(
                text=f"{status_prefix}{status_text}",
                icon_url=avatar_url
            )

            await interaction.followup.send(embed=main_embed)
        except Exception as e:
            await func.report_error(e, "getting bot info")

async def setup(bot):
    """Set up the BotInfo cog."""
    await bot.add_cog(BotInfo(bot))