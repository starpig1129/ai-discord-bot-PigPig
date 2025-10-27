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
import sys
import os
import re
import traceback
import update
from function import func, ROOT_DIR, tokens, settings, update_json
import json
import logging
import asyncio
from typing import Optional
from discord.ext import commands, tasks
from itertools import cycle
from cogs.music_lib.state_manager import StateManager
from cogs.music_lib.ui_manager import UIManager
from gpt.core.action_dispatcher import ActionDispatcher
from gpt.core.response_generator import get_model_and_tokenizer
from gpt.core.message_handler import MessageHandler
from gpt.performance_monitor import PerformanceMonitor
from logs import TimedRotatingFileHandler
from cogs.memory.memory_manager import MemoryManager
import gpt.tools.builtin
from cogs.memory.exceptions import MemorySystemError

# 導入優化模組
from gpt.optimization_integration import (
    initialize_optimization_from_file,
    get_optimized_bot,
    process_optimized_request,
)
from gpt.optimization_config_manager import is_optimization_enabled
# 配置 logging
def setup_logger(server_name):
    # 1. 將根記錄器的預設級別設定為 WARNING
    # 這樣可以抑制所有未明確設定級別的記錄器的 INFO 和 DEBUG 訊息。
    logging.getLogger().setLevel(logging.WARNING)

    # 2. 明確將特定第三方函式庫的日誌級別也設定為 WARNING
    # 雖然根記錄器已經是 WARNING，但明確設定可以防止它們自己的程式碼
    # 以任何方式覆蓋級別。
    third_party_loggers = [
        "faiss", "WDM", "sqlalchemy", "httpx", "google_genai",
        "discord", "websockets", "cogs.memory", "gpt", "jieba"
    ]
    for logger_name in third_party_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # 3. 為我們的應用程式（每個 guild）設定特定的 logger
    logger = logging.getLogger(server_name)
    logger.setLevel(logging.INFO)  # 讓我們的應用程式日誌從 INFO 開始記錄

    # 確保只為每個 logger 添加一次 handler，以避免日誌重複
    if not logger.handlers:
        handler = TimedRotatingFileHandler(server_name)
        formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger
class PigPig(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        func.set_bot(self)
        self.loggers = {}
        # ActionDispatcher 將在 setup_hook 中被創建和注入
        self.action_dispatcher: Optional[ActionDispatcher] = None
        self.message_handler: Optional[MessageHandler] = None
        
        # 記憶系統初始化
        self.memory_manager: Optional[MemoryManager] = None
        self.memory_enabled = False
        
        # 音樂系統管理器
        self.state_manager = StateManager()
        self.ui_manager = UIManager(self)
        
        # 優化系統初始化
        self.optimization_enabled = False
        self.optimized_bot = None
        self.performance_monitor = PerformanceMonitor()
        
        self.status_cycle = cycle([
            (discord.ActivityType.listening, "大家的聲音"),
            (discord.ActivityType.playing, "泥巴 在 {n} 個伺服器裡")
        ])

    @tasks.loop(seconds=15)
    async def change_status_task(self):
        """每 15 秒更換一次機器人狀態"""
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
        """包裝 change_presence 以處理連線錯誤"""
        try:
            await self.change_presence(*args, **kwargs)
        except ConnectionResetError:
            print("Connection reset error while changing presence, retrying in 60 seconds...")
            await asyncio.sleep(60)

    def setup_logger_for_guild(self, guild_name):
        if guild_name not in self.loggers:
            self.loggers[guild_name] = setup_logger(guild_name)

    def get_logger_for_guild(self, guild_name):
        if guild_name in self.loggers:
            return self.loggers[guild_name]
        else:
            self.setup_logger_for_guild(guild_name)
            return self.loggers[guild_name]
        
    def setup_logger_for_guild(self, guild_name):
        if guild_name not in self.loggers:
            self.loggers[guild_name] = setup_logger(guild_name)

    async def initialize_memory_system(self):
        """初始化記憶系統"""
        try:
            # 檢查設定是否啟用記憶系統
            memory_config = settings.memory_system if hasattr(settings, 'memory_system') else {}
            if not memory_config.get("enabled", False):
                print("記憶系統已在設定中停用")
                return
            
            self.memory_manager = MemoryManager(self)
            self.memory_enabled = await self.memory_manager.initialize()
            
            if self.memory_enabled:
                print("記憶系統初始化成功")
            else:
                print("記憶系統初始化失敗")
                
        except Exception as e:
            print(f"記憶系統初始化失敗: {e}")
            self.memory_enabled = False
    
    async def initialize_optimization_system(self):
        """根據配置文件初始化各個優化模組。"""
        try:
            if not is_optimization_enabled():
                print("優化系統已在配置中停用。")
                self.optimization_enabled = False
                return

            print("正在初始化優化系統...")
            # 這裡不再初始化一個完整的 Bot，而是根據需要初始化各個模組
            # 例如，未來可以這樣做：
            # config = get_optimization_config()
            # if config.get('gemini_cache'):
            #     self.gemini_cache = GeminiCache()
            # if config.get('parallel_tools'):
            #     self.tool_executor = ParallelToolExecutor()
            
            # 目前，我們只設置一個標誌
            self.optimization_enabled = True
            print("優化系統初始化完成。")

        except Exception as e:
            print(f"優化系統初始化失敗: {e}")
            print("將使用傳統處理方式。")
            self.optimization_enabled = False
    
    async def store_message_to_memory(self, message: discord.Message):
        """將訊息儲存到記憶系統"""
        if not self.memory_enabled or not self.memory_manager:
            return
        
        try:
            # 過濾機器人訊息和非伺服器訊息
            if message.author.bot or not message.guild:
                return
            
            # 檢查頻道是否允許記憶功能
            channel_manager = self.get_cog('ChannelManager')
            if channel_manager:
                guild_id = str(message.guild.id)
                is_allowed, _, __ = channel_manager.is_allowed_channel(message.channel, guild_id)
                if not is_allowed:
                    return
            
            # 儲存訊息到記憶系統
            await self.memory_manager.store_message(message)
            
        except MemorySystemError as e:
            print(f"記憶系統儲存訊息失敗: {e}")
        except Exception as e:
            print(f"儲存訊息到記憶系統時發生未預期錯誤: {e}")
        
    async def on_message(self, message: discord.Message, /) -> None:
        if message.author.bot or not message.guild:
            return
        
        guild_name = message.guild.name
        self.setup_logger_for_guild(guild_name)
        logger = self.loggers[guild_name]
        
        logger.info(f'收到訊息: {message.content} (來自:伺服器:{message.guild},頻道:{message.channel.name},{message.author.name})')
        
        # 儲存訊息到記憶系統
        await self.store_message_to_memory(message)
        
        await self.process_commands(message)
        
        # 將訊息處理委派給 MessageHandler
        # 檢查訊息是否需要由機器人處理 (例如 @mention 或在特定頻道)
        channel_manager = self.get_cog('ChannelManager')
        if channel_manager:
            guild_id = str(message.guild.id)
            is_allowed, auto_response_enabled, channel_mode = channel_manager.is_allowed_channel(message.channel, guild_id)

            # 檢查是否為故事模式頻道
            if channel_mode == 'story':
                story_manager_cog = self.get_cog('StoryManagerCog')
                if story_manager_cog:
                    await story_manager_cog.handle_story_message(message)
                return # 故事模式下，不繼續執行一般訊息處理

            # 只有在允許的頻道且被提及或啟用自動回應時，才觸發 handle_message
            if is_allowed and (self.user.id in message.raw_mentions and not message.mention_everyone or auto_response_enabled):
                await self.message_handler.handle_message(message)
    
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return
        
        logger = self.get_logger_for_guild(before.guild.name)
        logger.info(
            f"訊息修改: 原訊息({before.content}) 新訊息({after.content}) 頻道:{before.channel.name}, 作者:{before.author}"
        )
        
        # 更新記憶系統中的訊息
        await self.store_message_to_memory(after)

        guild_id = str(after.guild.id)
        channel_manager = self.get_cog('ChannelManager')
        if channel_manager:
            is_allowed, _, __ = channel_manager.is_allowed_channel(after.channel, guild_id)
            if not is_allowed:
                return

        try:
            match = re.search(r"<@\d+>\s*(.*)", after.content)
            prompt = match.group(1)
        except AttributeError:  # 如果正則表達式沒有匹配到，會拋出 AttributeError
            prompt = after.content
        
        # 實現生成回應的邏輯
        if self.user.id in after.raw_mentions and not after.mention_everyone:
            try:
                # Fetch the bot's previous reply
                async for msg in after.channel.history(limit=50):
                    if msg.reference and msg.reference.message_id == before.id and msg.author.id == self.user.id:
                        await msg.delete()  # 删除之前的回复

                message_to_edit = await after.reply("思考中...")  # 创建新的回复
                execute_action = await self.action_dispatcher.choose_act(prompt, after, message_to_edit)
                await execute_action(message_to_edit, prompt, after)
            except Exception as e:
                await func.report_error(e, f"on_message_edit: {e}")
        
    async def setup_hook(self) -> None:
        # Loading all the module in `cogs` folder
        for module in os.listdir(ROOT_DIR + '/cogs'):
            # 過濾條件：
            # 1. 必須是 .py 文件
            # 2. 排除 __init__.py（包初始化文件）
            # 3. 排除以 _ 開頭的文件（私有模組）
            # 4. 排除以 . 開頭的文件（隱藏文件）
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

        # 初始化核心服務
        self.action_dispatcher = ActionDispatcher(self)
        self.message_handler = MessageHandler(self, self.action_dispatcher, self.performance_monitor)

        # 初始化記憶系統
        await self.initialize_memory_system()
        
        # 初始化優化系統
        await self.initialize_optimization_system()

        if settings.ipc_server.get("enable", False):
            await self.ipc.start()

        if not settings.version or settings.version != update.__version__:
            update_json("settings.json", new_data={"version": update.__version__})

        await self.tree.sync()

    async def on_ready(self):
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
                channel_info =f"channel_name: {channel.name},channel_id: {channel.id},channel_type: {str(channel.type)}"
                guild_info['channels'].append(channel_info)
            data['guilds'].append(guild_info)
            self.setup_logger_for_guild(guild.name)  # 設置每個伺服器的 logger
        try:
            model_management_cog = self.get_cog('ModelManagement')
            # if model_management_cog:
            #     await model_management_cog.reload_model()
        except Exception as e:
            await func.report_error(e, f"on_ready: {e}")
        # 將資料寫入 JSON 文件
        with open('logs/guilds_and_channels.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print('update succesfully guilds_and_channels.json')
        tokens.client_id = self.user.id
        
        # 啟動狀態更新任務
        self.change_status_task.start()

    async def _send_error_report(self, embed: discord.Embed):
        bug_report_channel_id = os.getenv("BUG_REPORT_CHANNEL_ID")
        if bug_report_channel_id:
            channel = self.get_channel(int(bug_report_channel_id))
            if channel:
                await channel.send(embed=embed)
            else:
                logger = self.get_logger_for_guild("Bot")
                logger.error(f"找不到指定的錯誤報告頻道: {bug_report_channel_id}")

    async def on_error(self, event_method: str, *args, **kwargs):
        # 取得 logger
        logger = self.get_logger_for_guild("Bot")

        # 記錄錯誤
        logger.error(f"事件 '{event_method}' 發生錯誤")
        logger.error(traceback.format_exc())
        print(f"事件 '{event_method}' 發生錯誤")
        print(traceback.format_exc())

        await func.report_error(sys.exc_info()[1], f"on_error event: {event_method}")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # 忽略某些錯誤
        ignored = (commands.CommandNotFound, commands.DisabledCommand)
        if isinstance(error, ignored):
            return

        # 取得 logger
        logger = self.get_logger_for_guild(ctx.guild.name if ctx.guild else "DirectMessage")

        # 記錄錯誤
        logger.error(f"指令 '{ctx.command}' 發生錯誤: {error}")
        logger.error("".join(traceback.format_exception(type(error), error, error.__traceback__)))
        print(f"指令 '{ctx.command}' 發生錯誤: {error}")
        print("".join(traceback.format_exception(type(error), error, error.__traceback__)))

        await func.report_error(error, f"on_command_error: {ctx.command}")

        await ctx.send(f"發生錯誤：{error}")
    
    async def close(self):
        """優雅關閉機器人和所有系統"""
        try:
            # 關閉記憶系統（先於 super().close()）
            if self.memory_manager:
                # 先嘗試優雅關閉 VectorManager（可重入，避免卡死）
                try:
                    vm = getattr(self.memory_manager, "vector_manager", None)
                    if vm and hasattr(vm, "shutdown"):
                        await vm.shutdown()
                except Exception as e:
                    print(f"關閉向量管理器時發生錯誤: {e}")

                # 若提供 shutdown，優先使用以確保外部資源先被釋放
                if hasattr(self.memory_manager, "shutdown"):
                    await self.memory_manager.shutdown()
                else:
                    await self.memory_manager.cleanup()
                print("記憶系統已優雅關閉")
            
            # 關閉優化系統
            if self.optimization_enabled and self.optimized_bot:
                await self.optimized_bot.shutdown()
                print("優化系統已優雅關閉")
            
            # 關閉父類（斷開 Discord 連線等）
            await super().close()

            # 優雅取消其餘所有仍在事件迴圈中的任務，避免 Task exception was never retrieved
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            # 最後關閉 asyncio 預設執行緒池，避免 threading._shutdown 掛起
            try:
                loop = asyncio.get_running_loop()
                await loop.shutdown_default_executor()
            except Exception as e:
                print(f"關閉預設執行緒池時發生錯誤: {e}")
        except Exception as e:
            print(f"關閉機器人時發生錯誤: {e}")
