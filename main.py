# MIT License

# Copyright (c) 2024 starpig1129

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import discord
import asyncio
import logging
import threading
import uuid
import os
from function import func
from bot import PigPig
from addons import base_config, tokens
from addons.update import VersionChecker
from addons.settings import update_config, logging_config
from dotenv import load_dotenv

load_dotenv()

class CommandCheck(discord.app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("該命令只能在群組中使用!")
            return False

        return await super().interaction_check(interaction)

# Setup the bot object
intents = discord.Intents.default()
intents.message_content = True if base_config.prefix else False
intents.members = True
member_cache = discord.MemberCacheFlags(
    voice=True,
    joined=False
)

bot = PigPig(
    command_prefix=base_config.prefix,
    help_command=None,
    tree_cls=CommandCheck,
    chunk_guilds_at_startup=False,
    member_cache_flags=member_cache,
    activity=discord.Activity(type=discord.ActivityType.playing, name="啟動中"),
    case_insensitive=True,
    intents=intents
)

# Initialize logging system using the unified logging architecture
# Use UnifiedLoggerManager for proper setup and configuration
from logs import get_unified_logger_manager

logger_manager = get_unified_logger_manager()
# Initialize the complete logging system including root logger
startup_logger = logger_manager.initialize_logging_system()

if __name__ == "__main__":
    # Background version check using new architecture
    def check_version_background():
        """Background version check that doesn't block startup"""
        try:
            # Use a separate event loop for the version check
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Initialize version checker with new architecture
                version_checker = VersionChecker(update_config.github)
                
                async def check_version_async():
                    try:
                        result = await version_checker.check_for_updates()
                        current_version = version_checker.get_current_version()
                        latest_version = result.get("latest_version", current_version)
                        
                        if latest_version != current_version:
                            startup_logger.warning(f"⚠️ Update Available: {latest_version} (Current: {current_version})")
                        else:
                            startup_logger.info(f"✅ Bot is up-to-date: {latest_version}")
                            
                    except Exception as e:
                        startup_logger.warning(f"⚠️ Version check failed: {str(e)[:50]}...")
                
                # Run the async check
                loop.run_until_complete(check_version_async())
                
            finally:
                loop.close()
                
        except Exception as e:
            startup_logger.warning(f"⚠️ Version check setup failed: {str(e)[:50]}...")
    
    # Start background version check in a separate thread
    version_check_thread = threading.Thread(target=check_version_background, daemon=True)
    version_check_thread.start()
    
    # Ensure we have a valid token
    if not tokens.token:
        startup_logger.error("❌ Bot token not found. Please check your .env file.")
        exit(1)
    
    try:
        # Enable console logging for bot
        os.environ['ENABLE_CONSOLE_LOGGING'] = 'true'
        
        # Use existing ColoredConsoleHandler from logs.py instead of custom one
        from logs import ColoredConsoleHandler, get_unified_logger_manager
        
        # Get unified logger manager for configuration
        logger_manager = get_unified_logger_manager()
        
        # Create colored console handler using existing system
        colored_handler = ColoredConsoleHandler(
            enable_colored_logs=True,
            simple_format=True,
            config=logger_manager.config
        )
        
        # Run bot with existing colored logging handler
        bot.run(str(tokens.token), log_handler=colored_handler)
    except KeyboardInterrupt:
        startup_logger.info("🛑 Manual shutdown initiated by user")
    finally:
        startup_logger.info("🧹 Final cleanup completed")