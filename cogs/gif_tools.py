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
from discord.ext import commands
from discord import app_commands
import json
import requests
import logging
import random
from typing import Optional
from addons.settings import TOKENS
from .language_manager import LanguageManager
import function as func

class GifTools(commands.Cog):
    """GIF 搜尋與管理工具。"""

    def __init__(self, bot):
        self.bot = bot
        tokens = TOKENS()
        self.tenor_api_key = tokens.tenor_api_key
        if not self.tenor_api_key:
            raise ValueError("TENOR_API_KEY not found in environment variables")
        self.logger = logging.getLogger('gif_tools')
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    async def search_gif(self, query: str, limit: int = 1) -> list:
        """搜尋 GIF。

        Args:
            query: 搜尋關鍵字。
            limit: 返回結果數量，預設為 1。
                  建議保持較小的數值以提高相關性。

        Returns:
            list: GIF URL 列表。如果搜尋失敗則返回空列表。
        """
        try:
            url = "https://tenor.googleapis.com/v2/search"
            params = {
                "q": query,
                "key": self.tenor_api_key,
                "client_key": "pigpig_discord_bot",
                "limit": limit,
                "random": "true"
            }
            
            search_log = self.lang_manager.translate(
                "0", "system", "gif_tools", "logs", "searching_gif", query=query
            ) if self.lang_manager else f"搜尋 GIF: {query}"
            self.logger.info(search_log)
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = json.loads(response.content)
                gif_urls = []
                for result in data.get("results", []):
                    media_formats = result.get("media_formats", {})
                    if "gif" in media_formats:
                        url = media_formats["gif"]["url"]
                        found_log = self.lang_manager.translate(
                            "0", "system", "gif_tools", "logs", "found_gif", url=url
                        ) if self.lang_manager else f"找到 GIF: {url}"
                        self.logger.debug(found_log)
                        gif_urls.append(url)
                return gif_urls
            else:
                api_error_log = self.lang_manager.translate(
                    "0", "system", "gif_tools", "logs", "api_error", status_code=response.status_code
                ) if self.lang_manager else f"Tenor API 回應錯誤: {response.status_code}"
                self.logger.error(api_error_log)
                self.logger.debug(f"回應內容: {response.text}")
                return []
            
        except Exception as e:
            await func.func.report_error(e, f"search_gif: {e}")
            search_error_log = self.lang_manager.translate(
                "0", "system", "gif_tools", "logs", "search_error", error=str(e)
            ) if self.lang_manager else f"GIF 搜尋錯誤: {e}"
            self.logger.error(search_error_log, exc_info=True)
            return []

    @app_commands.command(name="search_gif", description="搜尋 GIF")
    async def search_gif_command(self, interaction: discord.Interaction, query: str):
        """Discord 指令: 搜尋 GIF。"""
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)
            
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        
        gifs = await self.search_gif(query)
        if gifs:
            gif_url = random.choice(gifs)
            await interaction.followup.send(gif_url)
        else:
            not_found_message = self.lang_manager.translate(
                guild_id, "commands", "search_gif", "responses", "not_found"
            ) if self.lang_manager else "找不到相關的 GIF。"
            await interaction.followup.send(not_found_message)

    async def get_gif_url(self, query: str) -> str:
        """取得隨機一個符合搜尋條件的 GIF URL。

        Args:
            query: 搜尋關鍵字。
                  例如："happy cat", "sad dog" 等描述性短語。

        Returns:
            str: GIF URL，如果找不到則返回空字串。
        """
        try:
            # 預處理搜尋關鍵字
            query = query.strip()
            if not query:
                warning_log = self.lang_manager.translate(
                    "0", "system", "gif_tools", "logs", "empty_query_warning"
                ) if self.lang_manager else "空的搜尋關鍵字"
                self.logger.warning(warning_log)
                return ""
                
            gifs = await self.search_gif(query)
            if gifs:
                chosen_gif = random.choice(gifs)
                chosen_log = self.lang_manager.translate(
                    "0", "system", "gif_tools", "logs", "found_gif", url=chosen_gif
                ) if self.lang_manager else f"選擇了 GIF: {chosen_gif} (關鍵字: {query})"
                self.logger.info(chosen_log)
                return chosen_gif
            return ""
        except Exception as e:
            await func.func.report_error(e, f"get_gif_url: {e}")
            error_log = self.lang_manager.translate(
                "0", "system", "gif_tools", "logs", "get_url_error", error=str(e)
            ) if self.lang_manager else f"取得 GIF URL 時發生錯誤: {e}"
            self.logger.error(error_log, exc_info=True)
            return ""

async def setup(bot):
    await bot.add_cog(GifTools(bot))