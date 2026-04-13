import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional
from addons.logging import get_logger
from function import func
from .language_manager import LanguageManager

log = get_logger(server_id="Bot", source=__name__)

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    def _translate(self, guild_id: str, *keys: str, default: str) -> str:
        """Helper to translate with a safe fallback when keys are missing."""
        if self.lang_manager:
            translated = self.lang_manager.translate(guild_id, *keys)
            if translated and not translated.startswith("[Translation not found"):
                return translated
        return default

    def _chunk_field_values(self, lines: List[str], limit: int = 1024) -> List[str]:
        """Split command lines into chunks that respect Discord's 1024-char field limit."""
        if not lines:
            return []

        chunks: List[str] = []
        current: List[str] = []
        length = 0

        for line in lines:
            addition = len(line) + (1 if current else 0)
            if addition + length > limit:
                chunks.append("\n".join(current))
                current = [line]
                length = len(line)
            else:
                current.append(line)
                length += addition

        if current:
            chunks.append("\n".join(current))

        return chunks

    def _create_embed_page(self, title: str, description: Optional[str]) -> discord.Embed:
        """Create a new embed page for the help command."""
        return discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )

    def _build_help_embeds(self, guild_id: str, title: str, description: str) -> List[discord.Embed]:
        """Construct one or more embeds while respecting Discord limits."""
        embeds: List[discord.Embed] = []
        current_embed = self._create_embed_page(title, description)

        for cog_name, cog in self.bot.cogs.items():
            cog_commands = cog.get_app_commands()
            if not cog_commands:
                continue

            cog_description = self._translate(
                guild_id,
                "system",
                cog_name.lower(),
                "description",
                default=cog.__doc__ or self._translate(guild_id, "general", "no_description", default="無描述")
            )

            command_lines = []
            for cmd in cog_commands:
                command_name = cmd.name
                command_desc = self._translate(
                    guild_id,
                    "commands",
                    command_name,
                    "description",
                    default=cmd.description or self._translate(guild_id, "general", "no_description", default="無描述")
                )
                command_lines.append(f"`/{command_name}`: {command_desc}")

            if not command_lines:
                continue

            field_name = f"**{cog_name}** ({cog_description})"
            if len(field_name) > 256:
                field_name = f"{field_name[:253]}..."

            for value_chunk in self._chunk_field_values(command_lines):
                # Start a new embed page if adding this field would exceed limits
                if len(current_embed.fields) >= 25 or len(current_embed) + len(field_name) + len(value_chunk) > 6000:
                    embeds.append(current_embed)
                    current_embed = self._create_embed_page(title, None)

                current_embed.add_field(
                    name=field_name,
                    value=value_chunk,
                    inline=False
                )

        if current_embed.fields:
            embeds.append(current_embed)

        # Add page numbering for clarity
        total_pages = len(embeds)
        for index, embed in enumerate(embeds, start=1):
            embed.set_footer(text=f"Page {index}/{total_pages}")

        return embeds

    @app_commands.command(name="help", description="Display all commands")
    async def help_command(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        guild_id = str(interaction.guild_id) if interaction.guild_id else "0"

        title = self._translate(guild_id, "commands", "help", "help_title", default="指令幫助")
        description = self._translate(
            guild_id,
            "commands",
            "help",
            "help_description",
            default="顯示所有可用指令的詳細資訊"
        )

        try:
            embeds = self._build_help_embeds(guild_id, title, description)

            if not embeds:
                fallback = self._translate(
                    guild_id,
                    "commands",
                    "help",
                    "no_commands",
                    default="目前沒有可用的指令。"
                )
                await interaction.followup.send(fallback, ephemeral=True)
                return

            # Discord allows up to 10 embeds per message; send in batches if needed
            for start in range(0, len(embeds), 10):
                await interaction.followup.send(embeds=embeds[start:start + 10])

        except Exception as e:
            log.exception("Error building help response")
            asyncio.create_task(func.report_error(e, "building help response"))
            fallback_error = self._translate(
                guild_id,
                "commands",
                "help",
                "error_message",
                default="生成指令列表時發生錯誤，請稍後再試。"
            )
            await interaction.followup.send(fallback_error, ephemeral=True)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
