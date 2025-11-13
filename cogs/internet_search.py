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
from discord import app_commands
from discord.ext import commands
from google import genai
from google.genai import types
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
import json

from addons.settings import llm_config
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

    @app_commands.command(
        name="search",
        description="Search the web using Gemini grounding (preferred) or fallback to legacy scraping"
    )
    @app_commands.describe(type="Search type (general, youtube, eat)")
    @app_commands.choices(
        type=[
            app_commands.Choice(name="general", value="general"),
            app_commands.Choice(name="youtube", value="youtube"),
            app_commands.Choice(name="eat", value="eat"),
        ]
    )
    async def search_command(self, interaction: discord.Interaction, type: app_commands.Choice[str] = 'general', query: str = ''):
        """Slash command wrapper for internet_search.
    
        Delegates to internet_search and returns the textual result if available.
        Ensures Discord message length limits are respected by splitting long
        markdown outputs into multiple followups.
        """
        await interaction.response.defer(thinking=True)
        selected_type = type.value if type else "general"
        guild_id = str(interaction.guild_id) if interaction.guild_id is not None else None
    
        def _split_markdown(md: str, limit: int = 1900) -> list:
            """Split markdown text into chunks not exceeding `limit` chars.
    
            Splits on line boundaries to avoid breaking markdown formatting.
            """
            if not md:
                return []
            lines = md.splitlines(keepends=True)
            chunks = []
            cur = ""
            for ln in lines:
                if len(cur) + len(ln) > limit:
                    if cur:
                        chunks.append(cur)
                    # If single line itself is longer than limit, hard-split it
                    if len(ln) > limit:
                        start = 0
                        while start < len(ln):
                            chunks.append(ln[start:start + limit])
                            start += limit
                        cur = ""
                    else:
                        cur = ln
                else:
                    cur += ln
            if cur:
                chunks.append(cur)
            return chunks
    
        try:
            result = await self.internet_search(
                ctx=interaction,
                query=query,
                search_type=selected_type,
                message_to_edit=None,
                guild_id=guild_id,
            )
    
            if isinstance(result, str):
                # Respect Discord's 2000-char limit by splitting into followups
                chunks = _split_markdown(result, limit=1900)
                try:
                    if not chunks:
                        await interaction.followup.send(content=result[:1900])
                    else:
                        for chunk in chunks:
                            await interaction.followup.send(content=chunk)
                except Exception as send_err:
                    # Report and attempt a concise fallback message
                    await func.report_error(send_err, f"search_command send followup failed: {send_err}")
                    try:
                        short = (result[:1900] + "...") if len(result) > 1900 else result
                        await interaction.followup.send(content=short)
                    except Exception:
                        # Give up silently to avoid raising further in the command handler
                        pass
            else:
                # Cog handled messaging (embed/view). Send a minimal localized confirmation if available.
                try:
                    confirmation = self.lang_manager.translate(
                        guild_id,
                        "commands",
                        "internet_search",
                        "responses",
                        "search_complete",
                        query=query
                    ) if self.lang_manager else f"Search for '{query}' completed."
                    # Trim confirmation if unexpectedly long
                    if len(confirmation) > 1900:
                        confirmation = confirmation[:1897] + "..."
                    await interaction.followup.send(content=confirmation)
                except Exception as notify_err:
                    await func.report_error(notify_err, f"search_command confirmation send failed: {notify_err}")
                    # Silently ignore notification failures to avoid interrupting flow
                    pass
        except Exception as e:
            await func.report_error(e, f"search_command: {e}")
            try:
                await interaction.followup.send(content=f"Search failed: {e}")
            except Exception:
                pass

    async def internet_search(self, ctx, query: str, search_type: str = "general", message_to_edit: Optional[discord.Message] = None, guild_id: str = ''):
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
        """Perform a web search using Gemini grounding, with a structured-system prompt.

        Behaviour:
        - If a Gemini/Google API key is available the cog will call the Gemini grounding
        search agent and instruct it (via a system prompt) to return a structured JSON
        response containing a concise answer and a list of sources.
        - If the Gemini call fails for any reason, the function falls back to the
        original Selenium scraping implementation so the bot remains functional.

        The agent is also instructed to prefer recent, authoritative sources and to
        include inline grounding citations which will be post-processed by add_citations.
        """

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            err = RuntimeError("Gemini API key not found in environment (GEMINI_API_KEY or GOOGLE_API_KEY)")
            await func.report_error(err, "google_search: missing Gemini API key")
            # Fallback to legacy scraping to preserve functionality
            return await self._legacy_google_search(ctx, query, message_to_edit)

        client = genai.Client(api_key=api_key)
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch()
        )

        # System prompt to instruct Gemini grounding agent to behave as a structured web
        system_prompt = (
            "You are a web research agent. Perform a grounding-enabled web search for the user's "
            "query and synthesize a concise, accurate answer. Prefer official and recent sources. "
            "Return the final output directly in Discord markdown format with these sections:\n\n"
            "**Answer:** One short paragraph.\n\n"
            "**Highlights:** Bullet list of up to 5 concise points.\n\n"
        )

        # Combine system prompt and user query into a single contents payload so the agent
        # understands both the instruction and the search target.
        contents = f"{system_prompt}\n\nUser query: {query}"

        config = types.GenerateContentConfig(
            tools=[grounding_tool, {"url_context": {}}]
        )

        try:
            def call_gemini():
                try:
                    # Use generate_content with the composed prompt
                    return client.models.generate_content(
                        model=llm_config.google_search_agent,
                        contents=contents,
                        config=config
                    )
                except Exception as inner:
                    raise

            response = await asyncio.to_thread(call_gemini)

            if not response:
                raise RuntimeError("Failed to extract text from Gemini grounding response")

            # Extract the main text content
            result_text = str(response.text)
            
            # Extract grounding metadata and append sources
            sources_text = self._extract_sources_from_grounding(response)
            if sources_text:
                result_text += f"\n\n{sources_text}"
            
            return result_text

        except Exception as e:
            await func.report_error(e, f"google_search gemini grounding: {e}")
            # Fallback: run legacy scraping to ensure the bot still returns useful results
            return await self._legacy_google_search(ctx, query, message_to_edit)


    def _extract_sources_from_grounding(self, response):
        """Extract source URLs and titles from Gemini grounding metadata.
        
        Args:
            response: The Gemini API response object
            
        Returns:
            A formatted markdown string with sources, or empty string if no sources found
        """
        try:
            # Navigate through the response structure to find grounding metadata
            if not hasattr(response, 'candidates') or not response.candidates:
                return ""
            
            candidate = response.candidates[0]
            
            # Check if grounding_metadata exists
            if not hasattr(candidate, 'grounding_metadata'):
                return ""
            
            grounding_metadata = candidate.grounding_metadata
            
            # Extract grounding chunks (sources)
            if not hasattr(grounding_metadata, 'grounding_chunks') or not grounding_metadata.grounding_chunks:
                return ""
            
            sources = []
            seen_urls = set()  # To avoid duplicate sources
            
            for chunk in grounding_metadata.grounding_chunks:
                if hasattr(chunk, 'web') and chunk.web:
                    uri = getattr(chunk.web, 'uri', None)
                    title = getattr(chunk.web, 'title', None)
                    
                    if uri and uri not in seen_urls:
                        seen_urls.add(uri)
                        # Format: [title](url) or just [url](url) if no title
                        display_text = title if title else uri
                        sources.append(f"- [{display_text}]({uri})")
            
            if not sources:
                return ""
            
            # Format sources section
            sources_section = "**Sources:**\n" + "\n".join(sources)
            return sources_section
            
        except Exception as e:
            # Log the error but don't fail the entire search
            print(f"Warning: Failed to extract sources from grounding metadata: {e}")
            asyncio.create_task(func.report_error(e, f"google_search grounding metadata extraction: {e}"))
            return ""


    async def _legacy_google_search(self, ctx, query, message_to_edit=None):
        """Original Selenium-based Google scraping preserved as a fallback."""
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
