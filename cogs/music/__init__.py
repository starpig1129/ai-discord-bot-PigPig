from .player import YTMusic

async def setup(bot):
    cog = YTMusic(bot)  # Regular synchronous initialization
    await cog.setup_hook()  # Async initialization
    await bot.add_cog(cog)
