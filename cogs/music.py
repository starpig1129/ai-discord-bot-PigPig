"""
Discord Music Bot Cog - Entry Point
This module serves as the entry point for the music functionality.
The actual implementation is modularized in the music/ directory.
"""

from .music.player import YTMusic

async def setup(bot):
    """Initialize the music cog"""
    cog = YTMusic(bot)
    await cog.setup_hook()  # Initialize async components
    await bot.add_cog(cog)

__all__ = ['setup', 'YTMusic']
