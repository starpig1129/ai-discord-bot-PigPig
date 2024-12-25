from .player import YTMusic

async def setup(bot):
    await bot.add_cog(YTMusic(bot))
