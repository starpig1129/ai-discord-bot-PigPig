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
import re
from pymongo import MongoClient
from discord.ext import commands
from discord import app_commands
import discord
from gpt.gpt_response_gen import generate_response
from addons.settings import Settings

from typing import Optional
from .language_manager import LanguageManager

class UserDataCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings = Settings()
        self.client = MongoClient(self.settings.mongodb_uri)
        self.db = self.client["user_data"]
        self.collection = self.db["users"]
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    @app_commands.command(name="userdata", description="管理用戶數據")
    @app_commands.choices(action=[
        app_commands.Choice(name="讀取", value="read"),
        app_commands.Choice(name="保存", value="save")
    ])
    async def userdata_command(self, interaction: discord.Interaction, action: str, user: discord.User = None, user_data: str = None):
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        await interaction.response.defer(thinking=True)
        guild_id = str(interaction.guild_id)
        result = await self.manage_user_data(interaction, user or interaction.user, user_data, action, guild_id=guild_id)
        await interaction.followup.send(result)

    async def manage_user_data(self, interaction, user: discord.User, user_data: str = None, action: str = 'read', message_to_edit: discord.Message = None, guild_id: str = None):
        user_id = str(user.id)
        if message_to_edit:
            searching_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "userdata",
                "responses",
                "searching"
            )
            await message_to_edit.edit(content=searching_message)

        if action == 'read':
            document = self.collection.find_one({"user_id": user_id})
            if document:      
                data = document["user_data"]
                return self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "userdata",
                    "responses",
                    "data_found",
                    user_id=user_id,
                    data=data
                )
            else:
                return self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "userdata",
                    "responses",
                    "data_not_found",
                    user_id=user_id
                )

        elif action == 'save':
            if message_to_edit:
                updating_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "userdata",
                    "responses",
                    "updating"
                )
                await message_to_edit.edit(content=updating_message)
            document = self.collection.find_one({"user_id": user_id})
            if document:
                existing_data = document["user_data"]
                prompt = f"Current original data: {existing_data}\nnew data: {user_data}"
                system_prompt = 'Return user data based on original data and new data.'
                thread, streamer = await generate_response(prompt, system_prompt)
                new_data = ''.join([response for response in streamer]).replace("<|eot_id|>","")
                thread.join()
                self.collection.update_one({"user_id": user_id}, {"$set": {"user_data": new_data}})
                return self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "userdata",
                    "responses",
                    "data_updated",
                    user_id=user_id,
                    data=new_data
                )
            else:
                self.collection.insert_one({"user_id": user_id, "user_data": user_data})
                return self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "userdata",
                    "responses",
                    "data_created",
                    user_id=user_id,
                    data=user_data
                )
    
        else:
            return self.lang_manager.translate(
                guild_id,
                "commands",
                "userdata",
                "responses",
                "invalid_action"
            )

    async def manage_user_data_message(self, message, user_id=None, user_data=None, action='read',message_to_edit: discord.Message = None):
        if user_id == "<@user_id>" or user_id is None:
            user_id = str(message.author.id)
        else:
            match = re.search(r'\d+', user_id)
            user_id = match.group() if match else str(message.author.id)

        user = await self.bot.fetch_user(int(user_id))
        result = await self.manage_user_data(message, user, user_data, action,message_to_edit)
        
        return result

async def setup(bot):
    await bot.add_cog(UserDataCog(bot))
