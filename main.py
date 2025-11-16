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
from addons.settings import update_config
from logs import ColoredConsoleHandler
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

# Initialize logging system with minimal setup to prevent duplication
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()  # Clear ALL existing handlers first

# ENHANCED: Apply comprehensive third-party library suppression BEFORE any logger initialization
third_party_suppression = {
    # Database libraries - suppress completely to prevent standard format logs
    "sqlalchemy.engine.Engine": logging.CRITICAL,  # CRITICAL to completely suppress
    "sqlalchemy.engine.base": logging.CRITICAL,   # SQLAlchemy engine base
    "sqlalchemy.engine": logging.CRITICAL,        # SQLAlchemy engine general
    "sqlalchemy.pool": logging.CRITICAL,          # SQLAlchemy connection pool
    "sqlalchemy.pool.impl": logging.CRITICAL,     # SQLAlchemy pool implementations
    "sqlalchemy.dialects": logging.CRITICAL,      # SQLAlchemy dialects
    "sqlalchemy.dialects.sqlite": logging.CRITICAL, # SQLite dialect
    "sqlalchemy.dialects.mysql": logging.CRITICAL,  # MySQL dialect
    "sqlalchemy.dialects.postgresql": logging.CRITICAL, # PostgreSQL dialect
    "sqlalchemy.orm": logging.CRITICAL,           # SQLAlchemy ORM
    "sqlalchemy.orm.session": logging.CRITICAL,   # SQLAlchemy ORM session
    "sqlalchemy.orm.query": logging.CRITICAL,     # SQLAlchemy ORM query
    "sqlalchemy.orm.mapper": logging.CRITICAL,    # SQLAlchemy ORM mapper
    "sqlalchemy.sql": logging.CRITICAL,           # SQLAlchemy SQL compilation
    "sqlalchemy.util": logging.CRITICAL,          # SQLAlchemy utilities
    "sqlalchemy": logging.CRITICAL,               # Main SQLAlchemy logger
    "alembic": logging.CRITICAL,                  # Database migrations
    
    # HTTP libraries - suppress completely
    "httpx": logging.CRITICAL,  # CRITICAL to suppress HTTP request logs
    "httpx.client": logging.CRITICAL,
    "httpx._client": logging.CRITICAL,
    "urllib3.connectionpool": logging.CRITICAL,
    "urllib3.poolmanager": logging.CRITICAL,
    "urllib3": logging.CRITICAL,
    "urllib3.util": logging.CRITICAL,
    "requests": logging.CRITICAL,
    "requests.packages": logging.CRITICAL,
    "requests.models": logging.CRITICAL,
    "aiohttp": logging.CRITICAL,
    "aiohttp.client": logging.CRITICAL,
    "aiohttp.connector": logging.CRITICAL,
    
    # Web drivers - suppress completely
    "WDM": logging.CRITICAL,  # CRITICAL to suppress WebDriver manager logs
    "selenium": logging.CRITICAL,
    "selenium.webdriver": logging.CRITICAL,
    "selenium.common": logging.CRITICAL,
    "webdriver": logging.CRITICAL,
    "webdriver_manager": logging.CRITICAL,
    
    # System and utility libraries
    "jieba": logging.CRITICAL,
    "jieba.analyse": logging.CRITICAL,
    "jieba.posseg": logging.CRITICAL,
    "jieba.finalseg": logging.CRITICAL,
    "pkg_resources": logging.CRITICAL,  # Suppress deprecation warnings
    "setuptools": logging.CRITICAL,
    "pip._internal": logging.CRITICAL,
    "pip._internal.utils": logging.CRITICAL,
    
    # Discord and websockets - suppress verbose logs
    "discord": logging.WARNING,
    "discord.gateway": logging.WARNING,
    "discord.http": logging.WARNING,
    "discord.state": logging.WARNING,
    "discord.client": logging.WARNING,
    "discord.ext": logging.WARNING,
    "discord.ext.commands": logging.WARNING,
    "discord.ext.tasks": logging.CRITICAL,
    "discord.voice_client": logging.WARNING,
    "discord.message": logging.WARNING,
    "discord.user": logging.WARNING,
    "discord.guild": logging.WARNING,
    "websockets": logging.WARNING,
    "websockets.legacy": logging.WARNING,
    "websockets.protocol": logging.WARNING,
    "websockets.client": logging.WARNING,
}

# Apply suppression to ALL third-party loggers BEFORE setting up our handler
for lib_name, lib_level in third_party_suppression.items():
    lib_logger = logging.getLogger(lib_name)
    lib_logger.setLevel(lib_level)
    lib_logger.propagate = False  # Prevent propagation to root logger
    
    # Also suppress any child loggers
    for handler in lib_logger.handlers[:]:
        lib_logger.removeHandler(handler)

# Additional comprehensive suppression for ALL database-related loggers
# This catches any SQLAlchemy sub-loggers that might not be explicitly listed
db_logger_names = [
    "sqlalchemy.engine.Engine",
    "sqlalchemy.engine.base.Engine",
    "sqlalchemy.engine.base.Connection",
    "sqlalchemy.engine.base.Executable",
    "sqlalchemy.engine.result",
    "sqlalchemy.engine.strategies",
    "sqlalchemy.pool.impl.QueuePool",
    "sqlalchemy.pool.impl.LifoQueueProxy",
    "sqlalchemy.pool.impl.StackedSharedProxy",
    "sqlalchemy.pool.events",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.mysql",
    "sqlalchemy.dialects.postgresql",
    "sqlalchemy.orm.session",
    "sqlalchemy.orm.query",
    "sqlalchemy.orm.mapper",
    "sqlalchemy.orm.relationships",
    "sqlalchemy.orm.attributes",
    "sqlalchemy.orm.util",
    "sqlalchemy.sql.elements",
    "sqlalchemy.sql.selectable",
    "sqlalchemy.sql.dml",
    "sqlalchemy.sql.schema",
    "sqlalchemy.sql.types",
    "sqlalchemy.util.langhelpers",
    "sqlalchemy.util.concurrency",
]

for db_logger_name in db_logger_names:
    db_logger = logging.getLogger(db_logger_name)
    db_logger.setLevel(logging.CRITICAL)
    db_logger.propagate = False
    while db_logger.handlers:
        db_logger.removeHandler(db_logger.handlers[0])

# Create a simple startup logger with ONLY colored console handler (NO root logger duplication)
startup_logger = logging.getLogger("STARTUP")
startup_logger.setLevel(logging.WARNING)  # Only show warnings and errors for startup
startup_logger.propagate = False  # Prevent propagation to root logger

# Add ONLY the colored console handler to startup logger with SIMPLE format
console_handler = ColoredConsoleHandler(enable_colored_logs=True, simple_format=True)
startup_logger.addHandler(console_handler)

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
        bot.run(str(tokens.token), log_handler=None)
    except KeyboardInterrupt:
        startup_logger.info("🛑 Manual shutdown initiated by user")
    finally:
        startup_logger.info("🧹 Final cleanup completed")