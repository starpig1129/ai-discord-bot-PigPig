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
import function as func
import json
import logging
import asyncio
from typing import Optional
from discord.ext import commands
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
    # 減少第三方套件的日誌等級
    logging.getLogger("faiss").setLevel(logging.WARNING)
    logging.getLogger("WDM").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)
    logging.getLogger("discord").setLevel(logging.WARNING)

    logger = logging.getLogger(server_name)
    logger.setLevel(logging.INFO)
    handler = TimedRotatingFileHandler(server_name)
    formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
class PigPig(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.loggers = {}
        # ActionDispatcher 將在 setup_hook 中被創建和注入
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
            memory_config = func.settings.memory_system if hasattr(func.settings, 'memory_system') else {}
            if not memory_config.get("enabled", False):
                print("記憶系統已在設定中停用")
                return
            
            self.memory_manager = MemoryManager()
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
            is_allowed, auto_response_enabled, _ = channel_manager.is_allowed_channel(message.channel, guild_id)
            
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
                print(e)
        
    async def setup_hook(self) -> None:
        # Loading all the module in `cogs` folder
        for module in os.listdir(func.ROOT_DIR + '/cogs'):
            # 過濾條件：
            # 1. 必須是 .py 文件
            # 2. 排除 __init__.py（包初始化文件）
            # 3. 排除以 _ 開頭的文件（私有模組）
            # 4. 排除以 . 開頭的文件（隱藏文件）
            if module == 'gen_img.py':
                # 由於 triton 套件安裝問題，暫時禁用 gen_img
                print(f"Skipping cog: {module[:-3]}")
                continue
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
        action_dispatcher = ActionDispatcher(self)
        self.message_handler = MessageHandler(self, action_dispatcher, self.performance_monitor)

        # 初始化記憶系統
        await self.initialize_memory_system()
        
        # 初始化優化系統
        await self.initialize_optimization_system()

        if func.settings.ipc_server.get("enable", False):
            await self.ipc.start()

        if not func.settings.version or func.settings.version != update.__version__:
            func.update_json("settings.json", new_data={"version": update.__version__})

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
            print(e)
        # 將資料寫入 JSON 文件
        with open('logs/guilds_and_channels.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print('update succesfully guilds_and_channels.json')
        func.tokens.client_id = self.user.id
        while True:
            await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="大家的聲音"))
            await asyncio.sleep(5)
    
    async def close(self):
        """優雅關閉機器人和所有系統"""
        try:
            # 關閉記憶系統
            if self.memory_manager:
                await self.memory_manager.cleanup()
                print("記憶系統已優雅關閉")
            
            # 關閉優化系統
            if self.optimization_enabled and self.optimized_bot:
                await self.optimized_bot.shutdown()
                print("優化系統已優雅關閉")
            
            # 關閉父類
            await super().close()
            
        except Exception as e:
            print(f"關閉機器人時發生錯誤: {e}")
