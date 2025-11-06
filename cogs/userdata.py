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
import logging
import json
import discord
from discord.ext import commands
from discord import app_commands
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from typing import Optional, Any, Union
from .language_manager import LanguageManager

from llm.model_manager import ModelManager
from llm.utils.send_message import safe_edit_message
from function import func
from addons.settings import memory_config, prompt_config
# 備用翻譯字典
FALLBACK_TRANSLATIONS = {
    "searching": "查詢用戶資料中...",
    "updating": "資料更新中...",
    "processing": "處理中...",
    "no_data_provided": "未提供任何資料。",
    "data_found": "用戶 <@{user_id}> 的資料：{data}",
    "data_not_found": "找不到用戶 <@{user_id}> 的資料。",
    "data_updated": "已更新用戶 <@{user_id}> 的資料：{data}",
    "data_created": "已為用戶 <@{user_id}> 創建資料：{data}",
    "sqlite_not_available": "SQLite 使用者管理系統未初始化",
    "invalid_action": "無效的操作。請使用 '讀取' 或 '保存'。",
    "database_error": "資料庫操作錯誤：{error}",
    "ai_processing_failed": "AI 處理用戶資料時發生錯誤：{error}",
    "update_failed": "更新用戶資料失敗：{error}",
    "analysis_failed": "資料分析失敗：{error}",
    "invalid_user": "無效的用戶 ID"
}


class UserDataCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None
        self.logger = logging.getLogger(__name__)
        self.user_manager = None
        self.db_manager = None

    def _translate(self, guild_id: str, *path, fallback_key: str = '', **kwargs) -> str:
        """統一的翻譯方法，包含備用機制"""
        if self.lang_manager:
            try:
                return self.lang_manager.translate(guild_id, *path, **kwargs)
            except Exception:
                pass
        
        # 使用備用翻譯
        if fallback_key and fallback_key in FALLBACK_TRANSLATIONS:
            try:
                return FALLBACK_TRANSLATIONS[fallback_key].format(**kwargs)
            except (KeyError, ValueError):
                return FALLBACK_TRANSLATIONS[fallback_key]
        
        # 最後的備用
        return "操作完成"

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器和使用者管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)
        # 初始化資料庫管理器和使用者管理器
        if not self.db_manager:
            from cogs.memory.database import DatabaseManager
            self.db_manager = DatabaseManager(memory_config.user_data_path, self.bot)
            self.user_manager = self.db_manager.user_manager

    def _get_guild_id_from_context(self, context: Union[discord.Interaction, discord.Message]) -> str:
        """從各種上下文中提取 guild_id"""
        if isinstance(context, discord.Interaction):
            # 處理來自斜線指令的互動
            if context.guild_id:
                return str(context.guild_id)
        elif isinstance(context, discord.Message) and context.guild:
            # 處理一般的訊息物件
            return str(context.guild.id)
        return ''

    @app_commands.command(name="userdata", description="管理用戶數據")
    @app_commands.choices(action=[
        app_commands.Choice(name="讀取", value="read"),
        app_commands.Choice(name="保存", value="save")
    ])
    async def userdata_command(self, interaction: discord.Interaction, 
                              action: str, 
                              user: Optional[Union[discord.User, discord.Member]] = None, 
                              user_data: str = ''):
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        await interaction.response.defer(thinking=True, ephemeral=True)
        
        result = await self.manage_user_data(
            interaction, user or interaction.user, user_data, action
        )
        
        await interaction.followup.send(result, ephemeral=True)

    async def _read_user_data(self, user_id: str, context: Any) -> str:
        """核心邏輯：讀取使用者資料"""
        guild_id = self._get_guild_id_from_context(context)
        try:
            user_mgr = self.user_manager
            if not user_mgr:
                return self._translate(
                    guild_id,
                    "system", "userdata", "errors", "sqlite_not_available",
                    fallback_key="sqlite_not_available"
                )

            user_info = await user_mgr.get_user_info(user_id)
            if user_info and user_info.user_data:
                return self._translate(
                    guild_id,
                    "commands", "userdata", "responses", "data_found",
                    fallback_key="data_found",
                    user_id=user_id,
                    data=user_info.user_data
                )
            else:
                return self._translate(
                    guild_id,
                    "commands", "userdata", "responses", "data_not_found",
                    fallback_key="data_not_found",
                    user_id=user_id
                )
        except Exception as e:
            try:
                await func.report_error(e, f"讀取使用者資料失敗 (使用者: {user_id})")
            except Exception:
                pass
            return self._translate(
                guild_id,
                "system", "userdata", "errors", "database_error",
                fallback_key="database_error",
                error=str(e)
            )

    async def _save_user_data(self, user_id: str, display_name: str, user_data: str, context: Any) -> str:
        """核心邏輯：儲存使用者資料（包含 AI 合併）"""
        guild_id = self._get_guild_id_from_context(context)
        try:
            user_mgr = self.user_manager
            if not user_mgr:
                return self._translate(
                    guild_id,
                    "system", "userdata", "errors", "sqlite_not_available",
                    fallback_key="sqlite_not_available"
                )

            user_info = await user_mgr.get_user_info(user_id)
            
            if user_info and user_info.user_data:
                # 使用 AI 智慧合併新舊資料
                existing_data = user_info.user_data
                
                # 從 addons/settings 載入 system_prompt
                system_prompt = prompt_config.get_system_prompt('user_data_agent')
                
                # 降級到硬編碼的 fallback prompt
                if not system_prompt:
                    system_prompt = '''You are a professional user data management assistant.
Intelligently merge existing user data with new data to return complete and accurate user information.
Maintain data integrity and consistency while avoiding duplicate information.
Always respond in Traditional Chinese.'''
                
                try:
                    # 取得註冊於 ModelManager 的 agent 型別 user_data_model
                    model = ModelManager().get_model("user_data_model")
                    if model is None:
                        raise RuntimeError("user_data_model not available")
                    agent = create_agent(model=model,
                                         tools=[],
                                         system_prompt=system_prompt)
                    
                    # 將既有資料與新資料包成 LangChain 標準 messages 格式
                    prompt_text = f"""Existing data: {json.dumps({'existing_data': existing_data}, ensure_ascii=False)}

New data: {json.dumps({'new_data': user_data}, ensure_ascii=False)}

Merge these intelligently and return complete user information."""
                    
                    # 使用 LangChain agent 的 ainvoke 進行非同步呼叫，取得回傳結果字典
                    response = await agent.ainvoke({"messages": [HumanMessage(content=prompt_text)]})
                    
                    # 從回應中提取文本內容
                    if isinstance(response, dict) and "messages" in response and response["messages"]:
                        new_data = response["messages"][-1].content
                    else:
                        new_data = str(response)
                    
                    # 若模型回傳結構化資料，轉成字串；並清理特殊終止標記
                    if isinstance(new_data, (dict, list)):
                        new_data = json.dumps(new_data, ensure_ascii=False)
                    
                except Exception as e:
                    try:
                        await func.report_error(e, f"AI 處理使用者資料失敗 (使用者: {user_id})")
                    except Exception:
                        pass
                    return self._translate(
                        guild_id,
                        "system", "userdata", "errors", "ai_processing_failed",
                        fallback_key="ai_processing_failed",
                        error=str(e)
                    )
                
                # 更新使用者資料
                success = await user_mgr.update_user_data(user_id, new_data, display_name)
                if success:
                    return self._translate(
                        guild_id,
                        "commands", "userdata", "responses", "data_updated",
                        fallback_key="data_updated",
                        user_id=user_id,
                        data=new_data
                    )
                else:
                    try:
                        await func.report_error(Exception("資料庫更新失敗"), f"更新使用者資料失敗 (使用者: {user_id})")
                    except Exception:
                        pass
                    return self._translate(
                        guild_id,
                        "system", "userdata", "errors", "update_failed",
                        fallback_key="update_failed",
                        error="資料庫更新失敗"
                    )
            else:
                # 建立新使用者資料
                success = await user_mgr.update_user_data(user_id, user_data, display_name)
                if success:
                    return self._translate(
                        guild_id,
                        "commands", "userdata", "responses", "data_created",
                        fallback_key="data_created",
                        user_id=user_id,
                        data=user_data
                    )
                else:
                    try:
                        await func.report_error(Exception("資料庫建立失敗"), f"建立使用者資料失敗 (使用者: {user_id})")
                    except Exception:
                        pass
                    return self._translate(
                        guild_id,
                        "system", "userdata", "errors", "update_failed",
                        fallback_key="update_failed",
                        error="資料庫建立失敗"
                    )
                    
        except Exception as e:
            try:
                await func.report_error(e, f"儲存使用者資料失敗 (使用者: {user_id})")
            except Exception:
                pass
            return self._translate(
                guild_id,
                "system", "userdata", "errors", "update_failed",
                fallback_key="update_failed",
                error=str(e)
            )

    async def manage_user_data(self, context: Any, user: Union[discord.User, discord.Member],
                               user_data: str = '', action: str = 'read',
                               message_to_edit: Optional[discord.Message] = None):
        """管理使用者資料（使用 SQLite） - 分派器"""
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)
        
        guild_id = self._get_guild_id_from_context(context)
        
        if not self.user_manager:
            return self._translate(guild_id, "system", "userdata", "errors", "sqlite_not_available", fallback_key="sqlite_not_available")
        
        user_id = str(user.id)
        
        if message_to_edit:
            if action == 'read':
                message_key = "searching"
            elif action == 'save':
                message_key = "updating"
            else:
                message_key = "processing" # Generic fallback
            
            status_message = self._translate(guild_id, "commands", "userdata", "responses", message_key, fallback_key=message_key)
            await safe_edit_message(message_to_edit, status_message)

        if action == 'read':
            return await self._read_user_data(user_id, context)
        
        elif action == 'save':
            if user_data is None:
                 return self._translate(guild_id, "commands", "userdata", "errors", "no_data_provided", fallback_key="no_data_provided")
            return await self._save_user_data(user_id, user.display_name, user_data, context)
    
        else:
            return self._translate(guild_id, "commands", "userdata", "responses", "invalid_action", fallback_key="invalid_action")

    async def manage_user_data_message(self, message, user_id=None, user_data='',
                                     action='read', message_to_edit: Optional[discord.Message] = None):
        """從訊息管理使用者資料"""
        guild_id = self._get_guild_id_from_context(message)
        
        try:
            if user_id == "<@user_id>" or user_id is None:
                user_id = str(message.author.id)
            else:
                match = re.search(r'\d+', user_id)
                user_id = match.group() if match else str(message.author.id)

            try:
                user = await self.bot.fetch_user(int(user_id))
            except (ValueError, discord.NotFound):
                return self._translate(
                    guild_id,
                    "system",
                    "userdata",
                    "errors",
                    "invalid_user",
                    fallback_key="invalid_user"
                )
            
            result = await self.manage_user_data(
                message, user, user_data, action, message_to_edit
            )
            return result
            
        except Exception as e:
            return self._translate(
                guild_id,
                "system",
                "userdata",
                "errors",
                "analysis_failed",
                fallback_key="analysis_failed",
                error=str(e)
            )

    async def get_user_statistics(self) -> dict:
        """取得使用者統計資訊"""
        if not self.user_manager:
            return {"error": "使用者管理器未初始化"}
        
        try:
            return await self.user_manager.get_user_statistics()
        except Exception as e:
            self.logger.error(f"取得使用者統計失敗: {e}")
            return {"error": str(e)}

    async def update_user_activity(self, user_id: str, display_name: str = '') -> bool:
        """更新使用者活躍狀態"""
        if not self.user_manager:
            return False
        
        try:
            return await self.user_manager.update_user_activity(user_id, display_name)
        except Exception as e:
            self.logger.error(f"更新使用者活躍狀態失敗: {e}")
            return False


async def setup(bot):
    await bot.add_cog(UserDataCog(bot))
