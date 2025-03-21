"""
Discord Music Bot Module
This module provides music playback functionality for Discord servers using YouTube as the source.
"""

from .player import YTMusic

async def setup(bot):
    """Initialize the music cog"""
    cog = YTMusic(bot)
    await cog.setup_hook()  # Initialize async components
    await bot.add_cog(cog)

__all__ = ['setup', 'YTMusic']
