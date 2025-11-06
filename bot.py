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

"""Discord bot main module.

This module contains the main bot class and configuration for a Discord bot
with music playback, message handling, and logging capabilities.
"""

import discord
import sys
import os
import traceback
import update
from function import func, ROOT_DIR
import json
import logging
import asyncio
from discord.ext import commands, tasks
from itertools import cycle
from cogs.music_lib.state_manager import StateManager
from cogs.music_lib.ui_manager import UIManager
from llm.orchestrator import Orchestrator
from logs import TimedRotatingFileHandler

from addons import tokens, base_config


def setup_logger(server_name):
    """Configure logging for a specific server.
    
    Sets up a logger with timed rotating file handler for a Discord server.
    Suppresses INFO and DEBUG messages from third-party libraries while
    maintaining INFO level logging for application-specific logs.
    
    Args:
        server_name (str): The name of the Discord server to create logger for.
        
    Returns:
        logging.Logger: Configured logger instance for the specified server.
        
    Note:
        - Root logger is set to WARNING level to suppress third-party logs
        - Application logger is set to INFO level
        - Uses TimedRotatingFileHandler for log rotation
        - Prevents duplicate handlers by checking existing handlers
    """
    # Set root logger default level to WARNING
    # This suppresses INFO and DEBUG messages from loggers without explicit level settings
    logging.getLogger().setLevel(logging.WARNING)

    # Explicitly set log level to WARNING for specific third-party libraries
    third_party_loggers = [
        "faiss", "WDM", "sqlalchemy", "httpx", "google_genai",
        "discord", "websockets", "cogs.memory", "gpt", "jieba"
    ]
    for logger_name in third_party_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # Set up specific logger for our application (per guild)
    logger = logging.getLogger(server_name)
    logger.setLevel(logging.INFO)  # Application logs start from INFO level

    # Ensure handler is added only once per logger to avoid duplicate logs
    if not logger.handlers:
        handler = TimedRotatingFileHandler(server_name)
        formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger


class PigPig(commands.Bot):
    """Main Discord bot class with music, messaging, and logging features.
    
    This bot extends discord.ext.commands.Bot with additional functionality including:
    - Per-guild logging system
    - Music playback state management
    - AI-powered message handling
    - Performance monitoring
    - Dynamic status updates
    
    Attributes:
        loggers (dict): Dictionary mapping guild names to their logger instances.
        state_manager (StateManager): Manager for music playback states.
        ui_manager (UIManager): Manager for music player UI components.
        status_cycle (itertools.cycle): Cycle iterator for rotating bot status messages.
        message_handler (MessageHandler): Handler for processing Discord messages.
    """
    
    def __init__(self, *args, **kwargs):
        """Initialize the PigPig bot instance.
        
        Args:
            *args: Variable length argument list passed to parent Bot class.
            **kwargs: Arbitrary keyword arguments passed to parent Bot class.
        """
        super().__init__(*args, **kwargs)
        func.set_bot(self)
        self.loggers = {}
        
        # Music system managers
        self.state_manager = StateManager()
        self.ui_manager = UIManager(self)
        
        
        self.status_cycle = cycle([
            (discord.ActivityType.listening, "大家的聲音"),
            (discord.ActivityType.playing, "泥巴 在 {n} 個伺服器裡")
        ])

    @tasks.loop(seconds=15)
    async def change_status_task(self):
        """Update bot status every 15 seconds.
        
        Cycles through predefined status messages, replacing placeholders
        with current bot statistics (e.g., number of guilds).
        
        Note:
            This is a discord.ext.tasks loop that runs continuously.
        """
        activity_type, name = next(self.status_cycle)
        
        if "{n}" in name:
            name = name.format(n=len(self.guilds))
        
        await self._change_presence(
            activity=discord.Activity(
                type=activity_type,
                name=name
            )
        )

    async def _change_presence(self, *args, **kwargs):
        """Wrapper for change_presence to handle connection errors.
        
        Attempts to change bot presence and handles ConnectionResetError
        by waiting 60 seconds before allowing retry.
        
        Args:
            *args: Variable length argument list passed to change_presence.
            **kwargs: Arbitrary keyword arguments passed to change_presence.
            
        Note:
            Prints error message and sleeps on ConnectionResetError.
        """
        try:
            await self.change_presence(*args, **kwargs)
        except ConnectionResetError:
            print("Connection reset error while changing presence, retrying in 60 seconds...")
            await asyncio.sleep(60)

    def get_logger_for_guild(self, guild_name):
        """Get or create logger for a specific guild.
        
        Args:
            guild_name (str): Name of the guild to get logger for.
            
        Returns:
            logging.Logger: Logger instance for the specified guild.
            
        Note:
            Creates a new logger if one doesn't exist for the guild.
        """
        if guild_name in self.loggers:
            return self.loggers[guild_name]
        else:
            self.setup_logger_for_guild(guild_name)
            return self.loggers[guild_name]
        
    def setup_logger_for_guild(self, guild_name):
        """Set up logger for a guild if it doesn't exist.
        
        Args:
            guild_name (str): Name of the guild to set up logger for.
            
        Note:
            Only creates logger if one doesn't already exist for the guild.
        """
        if guild_name not in self.loggers:
            self.loggers[guild_name] = setup_logger(guild_name)
        
    async def on_message(self, message: discord.Message, /) -> None:
        """Handle incoming Discord messages.
        
        Processes messages by:
        1. Setting up guild-specific logging
        2. Logging message details
        3. Ignoring bot messages
        4. Processing commands
        5. Handling special channel modes (story mode)
        6. Delegating to message handler for AI responses
        
        Args:
            message (discord.Message): The incoming Discord message object.
            
        Returns:
            None
            
        Note:
            - Ignores messages from DMs (no guild)
            - Ignores messages from other bots
            - Checks channel permissions and modes before processing
        """
        try:
            
            if not message.guild:
                return
            
            guild_name = message.guild.name
            self.setup_logger_for_guild(guild_name)
            logger = self.loggers[guild_name]
            
            logger.info(f'收到訊息: {message.content} (來自:伺服器:{message.guild},頻道:{message.channel.name},{message.author.name})')
            
            if message.author.bot:
                return
            
            await self.process_commands(message)
            
            # Delegate message processing to MessageHandler
            # Check if message should be handled by bot (e.g., @mention or in specific channel)
            channel_manager = self.get_cog('ChannelManager')
            if channel_manager:
                guild_id = str(message.guild.id)
                is_allowed, auto_response_enabled, channel_mode = channel_manager.is_allowed_channel(message.channel, guild_id)

                # Check if it's a story mode channel
                if channel_mode == 'story':
                    story_manager_cog = self.get_cog('StoryManagerCog')
                    if story_manager_cog:
                        await story_manager_cog.handle_story_message(message)
                    return  # In story mode, don't continue with general message processing

                # Only trigger handle_message if in allowed channel and mentioned or auto-response enabled
                if is_allowed and (self.user.id in message.raw_mentions and not message.mention_everyone or auto_response_enabled):
                    message_edit = await message.reply("...")
                    await self.orchestrator.handle_message(self,message_edit, message, logger)
        except Exception as e:
            await func.report_error(e, f"on_message: {e}")
            
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Handle edited Discord messages.
        
        When a message mentioning the bot is edited:
        1. Logs the edit details
        2. Deletes the bot's previous reply to the original message
        3. Generates a new response to the edited message
        4. Handles story mode channels specially
        
        Args:
            before (discord.Message): The message before editing.
            after (discord.Message): The message after editing.
            
        Returns:
            None
            
        Note:
            - Ignores edits in DMs
            - Ignores edits from bots
            - Only responds to messages that mention the bot
            - Searches last 50 messages to find bot's previous reply
        """
        try:
            if not before.guild:
                return
            
            logger = self.get_logger_for_guild(before.guild.name)
            logger.info(
                f"訊息修改: 原訊息({before.content}) 新訊息({after.content}) 頻道:{before.channel.name}, 作者:{before.author}"
            )
            if after.author.bot:
                return
            
            guild_id = str(after.guild.id)
            channel_manager = self.get_cog('ChannelManager')
            
            # Implement logic for generating responses
            if self.user.id in after.raw_mentions and not after.mention_everyone:
                    # Fetch the bot's previous reply
                    async for msg in after.channel.history(limit=50):
                        if msg.reference and msg.reference.message_id == before.id and msg.author.id == self.user.id:
                            await msg.delete()  # Delete previous reply
                    if channel_manager:
                        guild_id = str(after.guild.id)
                        is_allowed, auto_response_enabled, channel_mode = channel_manager.is_allowed_channel(after.channel, guild_id)
                        # Check if it's a story mode channel
                        if channel_mode == 'story':
                            story_manager_cog = self.get_cog('StoryManagerCog')
                            if story_manager_cog:
                                await story_manager_cog.handle_story_message(after)
                            return  # In story mode, don't continue with general message processing
                        
                        if is_allowed and (self.user.id in after.raw_mentions and not after.mention_everyone or auto_response_enabled):
                            message_edit = await after.reply("...")
                            await self.orchestrator.handle_message(self,message_edit, after, logger)
                            
        except Exception as e:
            await func.report_error(e, f"on_message_edit: {e}")
        
    async def setup_hook(self) -> None:
        """Set up bot before connecting to Discord.
        
        This method is called automatically by discord.py and performs:
        1. Loading all cog modules from the cogs folder
        2. Initializing MessageHandler
        3. Starting IPC server if enabled
        4. Updating version in settings
        5. Syncing command tree with Discord
        
        Returns:
            None
            
        Note:
            - Filters out __init__.py, private modules (_*), and hidden files (.*) 
            - Prints success/failure for each cog load attempt
            - Initializes performance monitoring
        """
        # Loading all the modules in `cogs` folder
        for module in os.listdir(ROOT_DIR + '/cogs'):
            # Filter conditions:
            # 1. Must be a .py file
            # 2. Exclude __init__.py (package initialization file)
            # 3. Exclude files starting with _ (private modules)
            # 4. Exclude files starting with . (hidden files)
            if (module.endswith('.py') and
                module != '__init__.py' and
                not module.startswith('_') and
                not module.startswith('.')):
                try:
                    await self.load_extension(f"cogs.{module[:-3]}")
                    print(f"Loaded {module[:-3]}")
                except Exception as e:
                    print(f"Failed to load {module[:-3]}: {e}")
                    print(traceback.format_exc())

        # Initialize core services
        self.orchestrator = Orchestrator()

        if base_config.ipc_server.get("enable", False):
            await self.ipc.start()

        if not base_config.version or base_config.version != update.__version__:
            func.update_json("settings.json", new_data={"version": update.__version__})

        await self.tree.sync()

    async def on_ready(self):
        """Handle bot ready event.
        
        Called when the bot has successfully connected to Discord. Performs:
        1. Prints bot information (name, ID, versions)
        2. Collects and saves guild/channel information to JSON
        3. Sets up loggers for all guilds
        4. Updates client ID in tokens
        5. Starts status update task
        
        Returns:
            None
            
        Note:
            - Creates logs/guilds_and_channels.json with server structure
            - Initializes logger for each guild the bot is in
            - Starts periodic status updates if not already running
        """
        print("------------------")
        print(f"Logging As {self.user}")
        print(f"Bot ID: {self.user.id}")
        print("------------------")
        print(f"Discord Version: {discord.__version__}")
        print(f"Python Version: {sys.version}")
        print("------------------")
        data = {}
        data['guilds'] = []
        for guild in self.guilds:
            guild_info = {
                'guild_name': guild.name,'guild_id': guild.id,
                'channels': []
            }
            for channel in guild.channels:
                channel_info = f"channel_name: {channel.name},channel_id: {channel.id},channel_type: {str(channel.type)}"
                guild_info['channels'].append(channel_info)
            data['guilds'].append(guild_info)
            self.setup_logger_for_guild(guild.name)  # Set up logger for each server
        # Write data to JSON file
        with open('logs/guilds_and_channels.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print('update succesfully guilds_and_channels.json')
        tokens.client_id = self.user.id
        
        # Start status update task
        if not self.change_status_task.is_running():
            self.change_status_task.start()

    async def on_error(self, event_method: str, *args, **kwargs):
        """Handle errors in event handlers.
        
        Called when an exception occurs in an event handler. Performs:
        1. Gets appropriate logger
        2. Logs error details and traceback
        3. Reports error through error reporting system
        
        Args:
            event_method (str): Name of the event method where error occurred.
            *args: Variable length argument list from the event.
            **kwargs: Arbitrary keyword arguments from the event.
            
        Returns:
            None
            
        Note:
            - Uses "Bot" as guild name for logger if guild context unavailable
            - Prints to console in addition to logging to file
        """
        # Get logger
        logger = self.get_logger_for_guild("Bot")

        # Log error
        logger.error(f"事件 '{event_method}' 發生錯誤")
        logger.error(traceback.format_exc())
        print(f"事件 '{event_method}' 發生錯誤")
        print(traceback.format_exc())

        await func.report_error(sys.exc_info()[1], f"on_error event: {event_method}")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Handle errors in command execution.
        
        Called when a command raises an exception. Performs:
        1. Ignores certain expected errors (CommandNotFound, DisabledCommand)
        2. Logs error details with full traceback
        3. Reports error through error reporting system
        4. Sends error message to channel
        
        Args:
            ctx (commands.Context): The invocation context where error occurred.
            error (commands.CommandError): The exception that was raised.
            
        Returns:
            None
            
        Note:
            - Uses guild name for logger, or "DirectMessage" for DMs
            - Gracefully handles failures in error message sending
            - Prints to console as fallback if logger unavailable
        """
        # Ignore certain errors
        ignored = (commands.CommandNotFound, commands.DisabledCommand)
        if isinstance(error, ignored):
            return

        # Try to get logger through bot
        logger = None
        if hasattr(self, "get_logger_for_guild"):
            guild_name = ctx.guild.name if getattr(ctx, "guild", None) else "DirectMessage"
            try:
                logger = self.get_logger_for_guild(guild_name)
            except Exception:
                logger = None

        # Log error
        if logger:
            logger.error(f"指令 '{ctx.command}' 發生錯誤: {error}")
            logger.error("".join(traceback.format_exception(type(error), error, error.__traceback__)))
        print(f"指令 '{ctx.command}' 發生錯誤: {error}")
        print("".join(traceback.format_exception(type(error), error, error.__traceback__)))

        await func.report_error(error, f"on_command_error: {ctx.command}")

        # Try to reply to channel (only log if reply fails, don't raise)
        try:
            await ctx.send("error on command execution.")
        except Exception as e:
            if logger:
                logger.exception("回覆錯誤訊息時發生例外")
            else:
                print(f"回覆錯誤訊息時發生例外: {e}")
            await func.report_error(ctx, error)
            
    async def send_error_report(self, embed: discord.Embed):
        bug_report_channel_id = tokens.bug_report_channel_id
        if bug_report_channel_id:
            channel = self.get_channel(int(bug_report_channel_id))
            if channel:
                await channel.send(embed=embed)
            else:
                logger = self.get_logger_for_guild("Bot")
                logger.error(f"找不到指定的錯誤報告頻道: {bug_report_channel_id}")
                
    async def close(self):
        """Gracefully shut down the bot and all systems.
        
        Performs cleanup in the following order:
        1. Calls parent class close() to disconnect from Discord
        2. Cancels all pending asyncio tasks
        3. Shuts down default executor thread pool
        
        Returns:
            None
            
        Note:
            - Prevents "Task exception was never retrieved" warnings
            - Avoids threading._shutdown hanging issues
            - Handles exceptions during shutdown gracefully
            - Should be called before program termination
        """
        try:         
            # Close parent class (disconnect from Discord, etc.)
            await super().close()

            # Gracefully cancel all remaining tasks in event loop to avoid Task exception was never retrieved
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            # Finally close asyncio default thread pool to avoid threading._shutdown hanging
            try:
                loop = asyncio.get_running_loop()
                await loop.shutdown_default_executor()
            except Exception as e:
                print(f"Error occurred while shutting down default executor: {e}")
        except Exception as e:
            print(f"Error occurred while closing bot: {e}")
