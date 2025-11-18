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
from function import func
from bot import PigPig
from addons import base_config, tokens
from addons.update import VersionChecker
from addons.settings import update_config
from addons.logging import get_logger
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
                        
                        # Acquire structured logger for main module
                        log = get_logger(server_id="Bot", source=__name__)
                        if latest_version != current_version:
                            log.warning(f"The latest version is {latest_version} ")
                            log.warning(f"and you are currently running version {current_version}. ")
                            log.warning(f"Run `python update.py -l` to update your bot!")
                        else:
                            log.info(f"Your PigPig Bot is up-to-date! - {latest_version}")
                                
                    except Exception as e:
                        # Log error but don't block startup
                        try:
                            asyncio.create_task(func.report_error(e, "main.py/version_check"))
                            log = get_logger(server_id="Bot", source=__name__)
                            log.error("Version check failed, but startup continues...")
                        except Exception:
                            # Fallback to stderr print if logging fails
                            print(f"\033[91mVersion check failed: {e}\033[0m")
                
                # Run the async check
                loop.run_until_complete(check_version_async())
                
            finally:
                loop.close()
                
        except Exception as e:
            try:
                # Note: Cannot use asyncio here due to variable scope issues
                print("\033[91mVersion check initialization failed, but startup continues...\033[0m")
            except Exception:
                print(f"\033[91mVersion check setup failed\033[0m")
    
    # Start background version check in a separate thread
    version_check_thread = threading.Thread(target=check_version_background, daemon=True)
    version_check_thread.start()
    
    # Ensure we have a valid token
    if not tokens.token:
        log = get_logger(server_id="Bot", source=__name__)
        log.error("Error: Bot token not found. Please check your .env file.")
        exit(1)
    
    try:
        bot.run(str(tokens.token), log_handler=None)
    except KeyboardInterrupt:
        print("收到 KeyboardInterrupt，使用者手動中斷，開始優雅關閉...")
    finally:
        try:
            asyncio.run(bot.close())
        except Exception as e:
            print(f"最終清理階段發生錯誤: {e}")
            try:
                asyncio.create_task(func.report_error(e, "main.py/finally"))
            except Exception:
                pass
