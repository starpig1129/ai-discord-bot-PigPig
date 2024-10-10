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
from discord.ext import commands
from gpt.choose_act import ActionHandler
from gpt.sendmessage import load_and_index_dialogue_history, save_vector_store, vector_stores
from gpt.gpt_response_gen import get_model_and_tokenizer
from logs import TimedRotatingFileHandler
# 配置 logging
def setup_logger(server_name):
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
        self.dialogue_history_file = './data/dialogue_history.json'
        self.vector_store_path = './data/vector_store'
        self.load_dialogue_history()
        load_and_index_dialogue_history(self.dialogue_history_file)
        self.loggers = {}
        self.action_handler = ActionHandler(self)
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

    def load_dialogue_history(self):
        """從檔案中讀取對話歷史"""
        try:
            with open(self.dialogue_history_file, 'r', encoding='utf-8') as file:
                self.dialogue_history = json.load(file)
        except FileNotFoundError:
            self.dialogue_history = {}

    def save_dialogue_history(self):
        """將對話歷史保存到檔案中"""
        with open(self.dialogue_history_file, 'w', encoding='utf-8') as file:
            json.dump(self.dialogue_history, file, ensure_ascii=False, indent=4)
        save_vector_store(vector_stores, self.vector_store_path)
        
    async def on_message(self, message: discord.Message, /) -> None:
        if message.author.bot or not message.guild:
            return
        
        guild_name = message.guild.name
        self.setup_logger_for_guild(guild_name)
        logger = self.loggers[guild_name]
        
        logger.info(f'收到訊息: {message.content} (來自:伺服器:{message.guild},頻道:{message.channel.name},{message.author.name})')
        await self.process_commands(message)
        
        channel_id = str(message.channel.id)
        if channel_id not in self.dialogue_history:
            self.dialogue_history[channel_id] = []
        
        try:
            match = re.search(r"<@\d+>\s*(.*)", message.content)
            prompt = match.group(1)
        except AttributeError:  # 如果正則表達式沒有匹配到，會拋出 AttributeError
            prompt = message.content
        
        self.dialogue_history[channel_id].append({"role": "user", "content": prompt})
        # 實現生成回應的邏輯
        if self.user.id in message.raw_mentions and not message.mention_everyone:
            # 發送初始訊息
            global global_model, global_tokenizer
    
            model, tokenizer = get_model_and_tokenizer()
            if model is None or tokenizer is None:
                await message.reply("豬腦休息中")
                self.save_dialogue_history()
                return
            
            message_to_edit = await message.reply("思考中...")
            try:
                execute_action = await self.action_handler.choose_act(prompt, message, message_to_edit)
                await execute_action(message_to_edit, self.dialogue_history, channel_id, prompt, message)
            except Exception as e:
                print(e)
        self.save_dialogue_history()
    
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return
        
        logger = self.get_logger_for_guild(before.guild.name)
        logger.info(
            f"訊息修改: 原訊息({before.content}) 新訊息({after.content}) 頻道:{before.channel.name}, 作者:{before.author}"
        )
        channel_id = str(after.channel.id)
        if channel_id not in self.dialogue_history:
            self.dialogue_history[channel_id] = []
        
        try:
            match = re.search(r"<@\d+>\s*(.*)", after.content)
            prompt = match.group(1)
        except AttributeError:  # 如果正則表達式沒有匹配到，會拋出 AttributeError
            prompt = after.content
        
        self.dialogue_history[channel_id].append({"role": "user", "content": prompt})
        
        # 實現生成回應的邏輯
        if self.user.id in after.raw_mentions and not after.mention_everyone:
            try:
                # Fetch the bot's previous reply
                async for msg in after.channel.history(limit=50):
                    if msg.reference and msg.reference.message_id == before.id and msg.author.id == self.user.id:
                        await msg.delete()  # 删除之前的回复

                message_to_edit = await after.reply("思考中...")  # 创建新的回复
                execute_action = await self.action_handler.choose_act(prompt, after, message_to_edit)
                await execute_action(message_to_edit, self.dialogue_history, channel_id, prompt, after)
            except Exception as e:
                print(e)
        self.save_dialogue_history()
        
    async def setup_hook(self) -> None:
        # Loading all the module in `cogs` folder
        for module in os.listdir(func.ROOT_DIR + '/cogs'):
            if module.endswith('.py'):
                try:
                    await self.load_extension(f"cogs.{module[:-3]}")
                    print(f"Loaded {module[:-3]}")
                except Exception as e:
                    print(traceback.format_exc())

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
            if model_management_cog:
                await model_management_cog.reload_LLM()
                await model_management_cog.reload_vqa_model()
        except Exception as e:
            print(e)
        # 將資料寫入 JSON 文件
        with open('logs/guilds_and_channels.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print('update succesfully guilds_and_channels.json')
        func.tokens.client_id = self.user.id
        