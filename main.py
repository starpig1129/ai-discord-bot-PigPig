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
import update
from function import func
from bot import PigPig
from addons import base_config,tokens
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
    update.check_version(with_msg=True)
    try:
        bot.run(tokens.token, log_handler=None)
    except KeyboardInterrupt:
        print("收到 KeyboardInterrupt，使用者手動中斷，開始優雅關閉...")
    finally:
        # 最終保險清理，避免 Task exception was never retrieved
        try:
            # 使用新的事件迴圈執行關閉（若先前已關閉則此呼叫為冪等）
            asyncio.run(bot.close())
        except Exception as e:
            print(f"最終清理階段發生錯誤: {e}")
            asyncio.create_task(func.report_error(e, "main.py/finally"))
