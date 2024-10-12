import discord
from discord.ext import commands
from discord import app_commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="顯示所有指令")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(title="指令列表", description="以下列出所有可用的指令：", color=discord.Color.blue())
        for cog_name, cog in self.bot.cogs.items():
            cog_commands = cog.get_app_commands()
            if cog_commands:
                cog_description = cog.__doc__ or "沒有描述"
                command_list = "\n".join([f"`/{cmd.name}`: {cmd.description}" for cmd in cog_commands])
                embed.add_field(name=f"**{cog_name}** ({cog_description})", value=command_list, inline=False)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
