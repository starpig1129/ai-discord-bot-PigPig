# cogs/episodic_memory.py
# Lightweight shim that delegates to the refactored implementation under cogs.memory.services.
# This shim deterministically requires bot.episodic_storage to be present before loading.
from cogs.memory.services.episodic_memory_service import EpisodicMemoryService as _EpisodicMemoryService
from discord.ext import commands
from function import func
import logging

log = logging.getLogger(__name__)

async def setup(bot: commands.Bot):
    # Deterministically use bot.episodic_storage. Do NOT fall back to legacy db_manager.
    storage = getattr(bot, "episodic_storage", None)
    if storage is None:
        log.error("Episodic storage missing on bot during episodic_memory cog setup.")
        await func.report_error(RuntimeError("EpisodicStorage missing"), "episodic_memory_cog_setup")
        # Fail fast to avoid creating a service with storage=None
        raise RuntimeError("EpisodicStorage missing. Ensure bot.episodic_storage is initialized before loading this cog.")
    await bot.add_cog(_EpisodicMemoryService(bot, storage))