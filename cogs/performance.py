# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
from discord import app_commands
import time
import humanize
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import PigPig

class PerformanceCog(commands.Cog):
    """一個用於顯示機器人性能指標的 Cog。"""

    def __init__(self, bot: "PigPig"):
        self.bot = bot

    @app_commands.command(name="perf_stats", description="顯示機器人的性能統計數據。")
    @commands.is_owner()
    async def perf_stats(self, interaction: discord.Interaction):
        """顯示機器人的性能統計數據。"""
        if not hasattr(self.bot, 'performance_monitor'):
            await interaction.response.send_message("性能監控器未啟用。", ephemeral=True)
            return

        stats = self.bot.performance_monitor.get_performance_stats()
        
        embed = discord.Embed(
            title="📈 機器人性能統計",
            description=f"自上次重置以來的性能數據。",
            color=discord.Color.blue()
        )

        # Session Duration
        duration_seconds = stats.get("session_duration_seconds", 0)
        # humanize.naturaldelta is not available, format it manually
        delta = humanize.naturaldelta(duration_seconds)
        embed.add_field(name="📊 運行時間", value=delta, inline=False)

        # Timers
        timers_data = stats.get("timers", {})
        if timers_data:
            value = ""
            for name, data in timers_data.items():
                value += f"**{name.replace('_', ' ').title()}**:\n"
                value += f"  - 平均: `{data['average_time']:.4f}s`\n"
                value += f"  - 總計: `{data['total_time']:.4f}s`\n"
                value += f"  - 次數: `{data['count']}`\n"
            embed.add_field(name="⏱️ 計時器", value=value, inline=True)

        # Counters
        counters_data = stats.get("counters", {})
        if counters_data:
            value = ""
            for name, count in counters_data.items():
                 if name == "cache_hit_rate":
                    value += f"**快取命中率**: `{count:.2%}`\n"
                 else:
                    value += f"**{name.replace('_', ' ').title()}**: `{count}`\n"
            embed.add_field(name="🔢 計數器", value=value, inline=True)
        
        embed.set_footer(text=f"報告生成時間: {discord.utils.format_dt(discord.utils.utcnow(), style='R')}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PerformanceCog(bot))