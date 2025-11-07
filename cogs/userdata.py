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
from langchain.agents.middleware import ModelCallLimitMiddleware

from typing import Optional, Any, Union
from .language_manager import LanguageManager

from llm.model_manager import ModelManager
from llm.utils.send_message import safe_edit_message
from function import func
from addons.settings import memory_config, prompt_config
# 備用翻譯字典
FALLBACK_TRANSLATIONS = {
    "searching": "正在查詢你的個人記憶...",
    "updating": "正在更新你的個人記憶...",
    "processing": "處理中...",
    "no_data_provided": "你沒有告訴我要記住什麼喔。",
    "data_found": "我目前記得關於你的事：\n{data}",
    "data_not_found": "我目前對你沒有任何特別的記憶。",
    "data_updated": "好的，我記住了！\n我更新後的記憶：\n{data}",
    "data_created": "好的，我記住了！\n我新增的記憶：\n{data}",
    "sqlite_not_available": "個人記憶系統未初始化",
    "invalid_action": "無效的操作。請使用 'save' 或 'show'。",
    "database_error": "資料庫操作錯誤：{error}",
    "ai_processing_failed": "AI 處理你的記憶時發生錯誤：{error}",
    "update_failed": "更新你的記憶失敗：{error}",
    "analysis_failed": "資料分析失敗：{error}",
    "invalid_user": "無效的用戶 ID"
}


class UserDataCog(commands.Cog):
    """
    管理使用者個人化資料的 Cog。

    提供 /memory 指令群組，讓使用者可以儲存或查看機器人對他們的
    特定記憶，例如偏好、暱稱或其他互動規則。
    """

    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None
        self.logger = logging.getLogger(__name__)
        self.user_manager = None
        self.db_manager = None

    memory_group = app_commands.Group(
        name="memory", 
        description="管理我對你的個人記憶與互動偏好"
    )

    def _translate(self, guild_id: str, *path, fallback_key: str = '', **kwargs) -> str:
        """
        統一的翻譯方法，包含備用機制。

        Args:
            guild_id: 伺服器 ID，用於決定語言。
            *path: 翻譯檔案中的路徑。
            fallback_key: 在 FALLBACK_TRANSLATIONS 中的備用鍵。
            **kwargs: 用於格式化翻譯字串的參數。

        Returns:
            翻譯後的字串。
        """
        if self.lang_manager:
            try:
                return self.lang_manager.translate(guild_id, *path, **kwargs)
            except Exception:
                pass
        
        if fallback_key and fallback_key in FALLBACK_TRANSLATIONS:
            try:
                return FALLBACK_TRANSLATIONS[fallback_key].format(**kwargs)
            except (KeyError, ValueError):
                return FALLBACK_TRANSLATIONS[fallback_key]
        
        return "操作完成"

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器和使用者管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)
        if not self.db_manager:
            from cogs.memory.database import DatabaseManager
            self.db_manager = DatabaseManager(memory_config.user_data_path, self.bot)
            self.user_manager = self.db_manager.user_manager

    def _get_guild_id_from_context(self, context: Union[discord.Interaction, discord.Message]) -> str:
        """
        從各種上下文中提取 guild_id。

        Args:
            context: Discord 的互動或訊息物件。

        Returns:
            伺服器 ID 字串，如果找不到則為空字串。
        """
        if isinstance(context, discord.Interaction):
            if context.guild_id:
                return str(context.guild_id)
        elif isinstance(context, discord.Message) and context.guild:
            return str(context.guild.id)
        return ''


    @memory_group.command(name="save", description="告訴我一件關於你的事，我會記住它（例如：你的名字或偏好）")
    @app_commands.describe(preference="你希望我記住的資訊（例如：'我的名字是小明' 或 '請叫我大師'）")
    async def memory_save(self, interaction: discord.Interaction, preference: str):
        """
        處理 /memory save 指令，儲存使用者的偏好設定。

        Args:
            interaction: Discord 互動物件。
            preference: 使用者希望被記住的字串資料。
        """
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        await interaction.response.defer(thinking=True, ephemeral=True)
        
        result = await self.manage_user_data(
            context=interaction,
            user=interaction.user,
            user_data=preference,
            action='save'  # 內部行動代號
        )
        
        await interaction.followup.send(result, ephemeral=True)

    # 【新增】/memory show 子指令
    @memory_group.command(name="show", description="查看我目前記得關於你的所有事情")
    async def memory_show(self, interaction: discord.Interaction):
        """
        處理 /memory show 指令，顯示已儲存的使用者偏好。

        Args:
            interaction: Discord 互動物件。
        """
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        await interaction.response.defer(thinking=True, ephemeral=True)
        
        result = await self.manage_user_data(
            context=interaction,
            user=interaction.user,
            user_data='',  # 讀取時不需要資料
            action='read'  # 內部行動代號
        )
        
        await interaction.followup.send(result, ephemeral=True)


    async def _read_user_data(self, user_id: str, context: Any) -> str:
        """
        核心邏輯：讀取並格式化使用者的儲存資料。

        Args:
            user_id: Discord 使用者 ID。
            context: 用於翻譯的互動或訊息上下文。

        Returns:
            包含使用者資料或「未找到」訊息的格式化字串。
        """
        guild_id = self._get_guild_id_from_context(context)
        try:
            user_mgr = self.user_manager
            if not user_mgr:
                return self._translate(
                    guild_id, "system", "userdata", "errors", "sqlite_not_available",
                    fallback_key="sqlite_not_available"
                )

            user_info = await user_mgr.get_user_info(user_id)
            if user_info and user_info.user_data:
                return self._translate(
                    guild_id, "commands", "userdata", "responses", "data_found",
                    fallback_key="data_found",
                    user_id=user_id, data=user_info.user_data
                )
            else:
                return self._translate(
                    guild_id, "commands", "userdata", "responses", "data_not_found",
                    fallback_key="data_not_found",
                    user_id=user_id
                )
        except Exception as e:
            try:
                await func.report_error(e, f"讀取使用者資料失敗 (使用者: {user_id})")
            except Exception:
                pass
            return self._translate(
                guild_id, "system", "userdata", "errors", "database_error",
                fallback_key="database_error", error=str(e)
            )

    async def _save_user_data(self, user_id: str, display_name: str, user_data: str, context: Any) -> str:
        """
        核心邏輯：儲存使用者資料（包含 AI 智慧合併）。

        Args:
            user_id: Discord 使用者 ID。
            display_name: 使用者的顯示名稱。
            user_data: 要儲存的新資料字串。
            context: 用於翻譯的互動或訊息上下文。

        Returns:
            操作結果的格式化字串（成功、失敗或錯誤）。
        """
        guild_id = self._get_guild_id_from_context(context)
        try:
            user_mgr = self.user_manager
            if not user_mgr:
                return self._translate(
                    guild_id, "system", "userdata", "errors", "sqlite_not_available",
                    fallback_key="sqlite_not_available"
                )

            user_info = await user_mgr.get_user_info(user_id)
            
            if user_info and user_info.user_data:
                existing_data = user_info.user_data
                system_prompt = prompt_config.get_system_prompt('user_data_agent')
                
                if not system_prompt:
                    system_prompt = '''You are a professional user data management assistant.
Intelligently merge existing user data with new data to return complete and accurate user information.
If the new data conflicts with the old data (e.g., a changed preference), the new data should take precedence and overwrite the conflicting part.
Maintain data integrity and consistency.
Always respond in Traditional Chinese.'''
                
                try:
                    try:
                        model, fallback = ModelManager().get_model("user_data_model")
                    except ValueError as e:
                        await func.report_error(e, "user_data_model not configured")
                        raise RuntimeError(f"user_data_model 未正確配置: {e}") from e
                    except Exception as e:
                        await func.report_error(e, "ModelManager.get_model failed for user_data_model")
                        raise RuntimeError(f"取得 user_data_model 失敗: {e}") from e
                    
                    agent = create_agent(model=model, tools=[],
                                         system_prompt=system_prompt,
                                         middleware=[
                                             ModelCallLimitMiddleware(run_limit=1, exit_behavior="end"),
                                             fallback,
                                         ])

                    prompt_text = f"""Existing data: {json.dumps({'existing_data': existing_data}, ensure_ascii=False)}

New data: {json.dumps({'new_data': user_data}, ensure_ascii=False)}

Merge these intelligently and return complete user information."""
                    
                    response = await agent.ainvoke({"messages": [HumanMessage(content=prompt_text)]})
                    
                    if isinstance(response, dict) and "messages" in response and response["messages"]:
                        new_data = response["messages"][-1].content
                    else:
                        new_data = str(response)
                    
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
                
                # 更新
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
                # 建立新資料
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
                               message_to_edit: Optional[discord.Message] = None) -> str:
        """
        管理使用者資料的分派器。

        根據 'action' 參數呼叫 _read_user_data 或 _save_user_data。

        Args:
            context: 互動或訊息上下文。
            user: 目標使用者物件。
            user_data: (可選) 要儲存的資料，僅 'save' 時使用。
            action: 'read' 或 'save'。
            message_to_edit: (可選) 在處理時要編輯的訊息物件。

        Returns:
            操作結果的字串。
        """
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
                message_key = "processing"
            
            status_message = self._translate(guild_id, "commands", "userdata", "responses", message_key, fallback_key=message_key)
            await safe_edit_message(message_to_edit, status_message)

        if action == 'read':
            return await self._read_user_data(user_id, context)
        
        elif action == 'save':
            if user_data is None or user_data.strip() == "":
                return self._translate(guild_id, "commands", "userdata", "errors", "no_data_provided", fallback_key="no_data_provided")
            return await self._save_user_data(user_id, user.display_name, user_data, context)
    
        else:
            return self._translate(guild_id, "commands", "userdata", "responses", "invalid_action", fallback_key="invalid_action")

    async def manage_user_data_message(self, message, user_id=None, user_data='',
                                        action='read', message_to_edit: Optional[discord.Message] = None):
        """
        (供內部工具使用) 從訊息觸發使用者資料管理。

        Args:
            message: 觸發的 Discord 訊息物件。
            user_id: (可選) 目標使用者 ID。
            user_data: (可選) 要儲存的資料。
            action: 'read' 或 'save'。
            message_to_edit: (可選) 要編輯的訊息。

        Returns:
            操作結果的字串。
        """
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
                    guild_id, "system", "userdata", "errors", "invalid_user",
                    fallback_key="invalid_user"
                )
            
            result = await self.manage_user_data(
                message, user, user_data, action, message_to_edit
            )
            return result
            
        except Exception as e:
            return self._translate(
                guild_id, "system", "userdata", "errors", "analysis_failed",
                fallback_key="analysis_failed", error=str(e)
            )

    async def get_user_statistics(self) -> dict:
        """
        取得使用者統計資訊。

        Returns:
            包含統計資料的字典，或錯誤訊息。
        """
        if not self.user_manager:
            return {"error": "使用者管理器未初始化"}
        
        try:
            return await self.user_manager.get_user_statistics()
        except Exception as e:
            self.logger.error(f"取得使用者統計失敗: {e}")
            return {"error": str(e)}

    async def update_user_activity(self, user_id: str, display_name: str = '') -> bool:
        """
        更新使用者活躍狀態。

        Args:
            user_id: 使用者 ID。
            display_name: (可選) 使用者顯示名稱。

        Returns:
            True (成功) 或 False (失敗)。
        """
        if not self.user_manager:
            return False
        
        try:
            return await self.user_manager.update_user_activity(user_id, display_name)
        except Exception as e:
            self.logger.error(f"更新使用者活躍狀態失敗: {e}")
            return False

async def setup(bot):
    cog = UserDataCog(bot)
    await bot.add_cog(cog)
