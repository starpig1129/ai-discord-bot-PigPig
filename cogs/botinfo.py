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
    """機器人資訊顯示 Cog"""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.utcnow()
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    def _format_uptime(self, uptime):
        """格式化運行時間"""
        days, remainder = divmod(int(uptime.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days:
            parts.append(f"{days}天")
        if hours:
            parts.append(f"{hours}小時")
        if minutes:
            parts.append(f"{minutes}分鐘")
        if seconds or not parts:
            parts.append(f"{seconds}秒")

        return " ".join(parts)

    @app_commands.command(name="botinfo", description="顯示機器人詳細資訊")
    async def botinfo(self, interaction: discord.Interaction):
        # 本地化命令描述
        if self.lang_manager:
            guild_id = str(interaction.guild_id) if interaction.guild_id else "0"
            localized_desc = self.lang_manager.translate(guild_id, "commands", "botinfo", "description")
            if localized_desc != "botinfo":
                self.botinfo.description = localized_desc

        try:
            """顯示機器人詳細資訊"""
            await interaction.response.defer()

            bot = interaction.client
            guild_id = str(interaction.guild_id) if interaction.guild_id else "0"

            # 計算運行時間
            uptime = datetime.utcnow() - self.start_time
            uptime_str = self._format_uptime(uptime)

            # 網路延遲
            latency = round(bot.latency * 1000, 2)

            # 系統資訊
            try:
                import resource
                memory_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KB to MB on Linux
                if platform.system() == "Windows":
                    memory_usage = memory_usage * 1024  # KB on Windows
            except:
                memory_usage = "N/A"

            # 檢查語言管理器是否可用
            if not self.lang_manager:
                # 如果語言管理器不可用，使用預設值
                title = "機器人資訊總覽"
                basic_stats_name = "基本統計"
                servers_label = "伺服器數量"
                users_label = "用戶數量"
                text_channels_label = "文字頻道"
                voice_channels_label = "語音頻道"
                loaded_cogs_label = "已載入 Cogs"
                performance_name = "效能監控"
                latency_label = "網路延遲"
                memory_usage_label = "記憶體使用"
                uptime_label = "運行時間"
                cogs_name = "功能模組"
                commands_label = "個命令"
                no_cogs_label = "無載入的模組"
                status_online = "線上"
                status_idle = "閒置"
                status_dnd = "請勿打擾"
                status_offline = "離線"
                status_unknown = "未知"
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

            # 主要 Embed
            main_embed = discord.Embed(
                title=title,
                color=discord.Color.from_rgb(114, 137, 218),
                timestamp=datetime.utcnow()
            )

            # 安全地取得用戶資訊
            user_name = getattr(bot.user, 'name', 'Unknown')
            discriminator = getattr(bot.user, 'discriminator', '0000')
            avatar_url = getattr(bot.user, 'display_avatar', getattr(bot.user, 'avatar', None))
            if avatar_url:
                avatar_url = avatar_url.url if hasattr(avatar_url, 'url') else str(avatar_url)

            main_embed.set_thumbnail(url=avatar_url)
            main_embed.set_author(name=f"{user_name}#{discriminator}", icon_url=avatar_url)

            # 基本統計資訊
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

            # 效能監控
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

            # 功能模組
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

            # 狀態指示器
            status_indicators = {
                discord.Status.online: status_online,
                discord.Status.idle: status_idle,
                discord.Status.dnd: status_dnd,
                discord.Status.offline: status_offline
            }

            bot_status = getattr(bot, 'status', discord.Status.offline)
            status_text = status_indicators.get(bot_status, status_unknown)
            main_embed.set_footer(
                text=f"狀態: {status_text}",
                icon_url=avatar_url
            )

            await interaction.followup.send(embed=main_embed)
        except Exception as e:
            await func.report_error(e, "getting bot info")

async def setup(bot):
    """設定 Cog"""
    await bot.add_cog(BotInfo(bot))