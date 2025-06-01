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

    @app_commands.command(name="help", description="Display all commands")
    async def help_command(self, interaction: discord.Interaction):
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        guild_id = str(interaction.guild_id)
        
        # 獲取本地化的標題和描述
        title = self.lang_manager.translate(guild_id, "general", "help_title") or "指令幫助"
        description = self.lang_manager.translate(guild_id, "general", "help_description") or "顯示所有可用指令的詳細資訊"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )

        # 遍歷所有 Cog 和命令
        for cog_name, cog in self.bot.cogs.items():
            cog_commands = cog.get_app_commands()
            if cog_commands:
                # 獲取 Cog 描述，優先使用翻譯，否則使用 docstring 或默認值
                cog_description = (
                    self.lang_manager.translate(guild_id, "system", cog_name.lower(), "description") or
                    cog.__doc__ or
                    self.lang_manager.translate(guild_id, "general", "no_description") or
                    "無描述"
                )
                
                # 本地化每個命令的描述
                command_list = []
                for cmd in cog_commands:
                    command_name = cmd.name
                    # 優先使用翻譯，否則使用原始描述
                    command_desc = (
                        self.lang_manager.translate(guild_id, "commands", command_name, "description") or
                        cmd.description or
                        self.lang_manager.translate(guild_id, "general", "no_description") or
                        "無描述"
                    )
                    command_list.append(f"`/{command_name}`: {command_desc}")
                
                embed.add_field(
                    name=f"**{cog_name}** ({cog_description})",
                    value="\n".join(command_list),
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
