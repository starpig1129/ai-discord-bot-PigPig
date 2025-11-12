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
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from youtube_search import YoutubeSearch
import random
import os

from cogs.eat.db.db import DB
from cogs.eat.embeds import eatEmbed
from cogs.eat.providers.googlemap_crawler import GoogleMapCrawler
from cogs.eat.train.train import Train
from cogs.eat.views import EatWhatView
import concurrent.futures
import asyncio

from typing import Optional
from .language_manager import LanguageManager
from llm.utils.send_message import safe_edit_message
from function import func

def install_driver():
    return ChromeDriverManager().install()

class InternetSearchCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DB()
        self.train = Train(db=self.db)
        self.map = GoogleMapCrawler()
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    async def internet_search(self, ctx, query: str, search_type: str = "general", message_to_edit: discord.Message = None, guild_id: str = None):
        if message_to_edit:
            searching_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "internet_search",
                "responses",
                "searching"
            )
            try:
                await safe_edit_message(message_to_edit, searching_message)
            except discord.errors.NotFound:
                # 原訊息不存在，改為送出新訊息以維持體驗
                fallback_text = f"🔍 {searching_message}" if searching_message else f"🔍 正在為您搜尋：{query}"
                try:
                    await ctx.channel.send(fallback_text)
                except Exception:
                    # 保底：忽略發送失敗，避免中斷後續流程
                    pass
                import logging
                logging.getLogger(__name__).info("internet_search: 原始訊息已不存在，已改為發送新訊息。")
        
        # 將外部傳入的 search_type 正規化，支援 'web' 作為一般網頁搜尋別名
        normalized_type = (search_type or "").strip().lower()
        if normalized_type == "web":
            # 將 'web' 對應到現有的一般搜尋邏輯
            normalized_type = "general"
            import logging
            logging.getLogger(__name__).info("internet_search: 收到 search_type='web'，已映射為 'general'。")
        else:
            # 若非已知型別，保留原字串，後續落入未知類型處理
            pass

        search_functions = {
            "general": self.google_search,
            "youtube": self.youtube_search,
            "eat": self.eat_search
        }
        
        search_func = search_functions.get(normalized_type)
        if search_func:
            if not guild_id and isinstance(ctx, discord.Interaction):
                guild_id = str(ctx.guild_id)
            elif not guild_id and hasattr(ctx, 'guild'):
                guild_id = str(ctx.guild.id)
                
            result = await search_func(ctx, query, message_to_edit)
            
            if isinstance(result, str):
                return result
            return None
        else:
            # 未知的 search_type，回傳本地化錯誤訊息，並記錄警告以便診斷
            import logging
            logging.getLogger(__name__).warning(f"internet_search: 未知的搜索類型：{search_type}")
            error_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "internet_search",
                "responses",
                "unknown_type",
                type=search_type
            )
            return error_message

    async def google_search(self, ctx, query, message_to_edit=None):
        guild_id = str(ctx.guild_id) if isinstance(ctx, discord.Interaction) else str(ctx.guild.id)
        chrome_options = self.get_chrome_options()

        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(install_driver)
                driver_path = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: future.result(timeout=10)
                )
                service = Service(driver_path)
        except (concurrent.futures.TimeoutError, Exception) as e:
            print(f"ChromeDriverManager timed out or failed: {e}, falling back to local driver")
            await func.report_error(e, f"google_search ChromeDriverManager: {e}")
            chrome_driver_path = './chromedriverlinux64/chromedriver'
            service = Service(executable_path=chrome_driver_path)
        
        with webdriver.Chrome(options=chrome_options, service=service) as driver:
            # Disable automation detection
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                '''
            })
            
            url = f"https://www.google.com/search?q={query}"
            driver.get(url)
            time.sleep(random.uniform(1.5, 3.5))  # Human-like delay
            html = driver.page_source

        soup = BeautifulSoup(html, 'html.parser')
        search_results = soup.select('.g')
        # Extract and add links to search results
        search_results_with_links = []
        for result in search_results[:8]:
            title = result.select_one('h3').text if result.select_one('h3') else 'No Title'
            snippet = result.select_one('.VwiC3b').text if result.select_one('.VwiC3b') else 'No Snippet'
            link = result.select_one('a')['href'] if result.select_one('a') else 'No Link'
            search_results_with_links.append(f"{title}\n{snippet}\n{link}")
        
        search = "\n\n".join(search_results_with_links)
        # Check for CAPTCHA
        if "Our systems have detected unusual traffic" in html:
            raise RuntimeError("Google blocked the request (CAPTCHA triggered)")
        return search


    @staticmethod
    def get_chrome_options():
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        return chrome_options


    @staticmethod
    async def send_error_message(ctx, message_to_edit, content):
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(content=content)
        else:
            try:
                await safe_edit_message(message_to_edit, content)
            except discord.errors.NotFound:
                import logging
                logging.getLogger(__name__).info("send_error_message: 臨時訊息不存在，略過文字訊息編輯。")

    async def youtube_search(self, ctx, query, message_to_edit=None):
        try:
            guild_id = str(ctx.guild_id) if isinstance(ctx, discord.Interaction) else str(ctx.guild.id)
            results = YoutubeSearch(query, max_results=5).to_dict()
            if not results:
                return self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "internet_search",
                    "responses",
                    "no_videos_found"
                )

            selected_result = random.choice(results)
            video_description = self.lang_manager.translate(
                guild_id,
                "commands",
                "internet_search",
                "responses",
                "youtube_result",
                title=selected_result['title'],
                channel=selected_result['channel'],
                views=selected_result['views'],
                url=f"https://www.youtube.com{selected_result['url_suffix']}"
            )
            return video_description
        except Exception as e:
            await func.report_error(e, f"youtube_search: {e}")
            return self.lang_manager.translate(
                guild_id,
                "commands",
                "internet_search",
                "responses",
                "search_failed",
                error=str(e)
            )


    async def eat_search(self, ctx, keyword: str = "_", message_to_edit: discord.Message = None):
        guild_id = str(ctx.guild_id) if isinstance(ctx, discord.Interaction) else str(ctx.guild.id)
        predict = None
        if keyword == "_":
            keywords_list = self.db.getKeywords()
            if len(keywords_list) == 0:
                return self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "internet_search",
                    "errors",
                    "eat_no_food"
                ) if self.lang_manager else "沒有這種食物喔"
            else:
                keyword = random.choice(keywords_list)[0]
                predict = self.train.predict(discord_id=str(ctx.guild.id))
        else:
            if len(self.db.checkKeyword(keyword=keyword)) == 0:
                self.db.storeKeyword(keyword)

        try:
            if predict is not None:
                result = self.map.search(predict)
                (title_pred, rate_pred, tag_pred, address_pred, url, reviews, menu) = result
                embed = eatEmbed(keyword=predict, title=title_pred, address=address_pred, rating=rate_pred)
                if len(self.db.checkKeyword(keyword=tag_pred)) == 0:
                    self.db.storeKeyword(tag_pred)
                id = self.db.storeSearchRecord(str(ctx.guild.id), title=title_pred, keyword=predict, map_rate=rate_pred, tag=tag_pred, map_address=address_pred)
            else:
                result = self.map.search(keyword)
                (title, rate, tag, address, url, reviews, menu) = result
                embed = eatEmbed(keyword=keyword, title=title, address=address, rating=rate)
                if len(self.db.checkKeyword(keyword=tag)) == 0:
                    self.db.storeKeyword(tag)
                id = self.db.storeSearchRecord(str(ctx.guild.id), title=title, keyword=keyword, map_rate=rate, tag=tag, map_address=address)

            view = EatWhatView(result=result, predict=predict, keyword=keyword, db=self.db, record_id=id, discord_id=str(ctx.guild.id))
            
            if isinstance(ctx, discord.Interaction):
                await ctx.followup.send(embed=embed, view=view)
            else:
                try:
                    await message_to_edit.edit(embed=embed, view=view)
                except discord.errors.NotFound:
                    import logging
                    logging.getLogger(__name__).info("eat_search: 臨時訊息不存在，略過結果訊息編輯。")

            self.train.genModel(str(ctx.guild.id))
            return None  
        except Exception as e:
            await func.report_error(e, f"eat_search: {e}")
            keyword_to_use = keyword if predict is None else predict
            return self.lang_manager.translate(
                guild_id,
                "commands",
                "internet_search",
                "errors",
                "eat_system_error",
                keyword=keyword_to_use,
                error=str(e)
            ) if self.lang_manager else f"原本想推薦你吃 {keyword_to_use}，但很抱歉系統出錯了QQ: {str(e)}"

async def setup(bot):
    await bot.add_cog(InternetSearchCog(bot))
