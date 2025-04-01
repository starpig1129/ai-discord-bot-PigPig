import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from .language_manager import LanguageManager

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    @app_commands.command(name="help", description="顯示所有指令")
    async def help_command(self, interaction: discord.Interaction):
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        guild_id = str(interaction.guild_id)
        
        # 獲取本地化的標題和描述
        title = self.lang_manager.translate(guild_id, "commands", "help", "description")
        description = self.lang_manager.translate(guild_id, "commands", "help", "description")
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )

        # 遍歷所有 Cog 和命令
        for cog_name, cog in self.bot.cogs.items():
            cog_commands = cog.get_app_commands()
            if cog_commands:
                cog_description = cog.__doc__ or self.lang_manager.translate(
                    guild_id, "general", "no_description"
                )
                
                # 本地化每個命令的描述
                command_list = []
                for cmd in cog_commands:
                    command_name = cmd.name
                    command_desc = self.lang_manager.translate(
                        guild_id,
                        "commands",
                        command_name,
                        "description"
                    ) or cmd.description
                    command_list.append(f"`/{command_name}`: {command_desc}")
                
                embed.add_field(
                    name=f"**{cog_name}** ({cog_description})",
                    value="\n".join(command_list),
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
