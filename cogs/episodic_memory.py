# cogs/episodic_memory_service.py
# Lightweight shim that delegates to the refactored implementation under cogs.memory.services.
# Keeps backward compatibility for existing cog loader while using the new EpisodicMemoryService.
 
from cogs.memory.services.episodic_memory_service import EpisodicMemoryService as _EpisodicMemoryService
from discord.ext import commands
 
async def setup(bot: commands.Bot):
    # Provide bot.db_manager as storage for backward compatibility if present.
    storage = getattr(bot, "db_manager", None)
    await bot.add_cog(_EpisodicMemoryService(bot, storage))