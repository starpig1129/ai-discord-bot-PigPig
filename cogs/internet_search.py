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
from cogs.eat.embeds import browseEmbed, loadingEmbed
from cogs.eat.providers import get_restaurant_provider
from cogs.eat.recommender import WeightedRecommender
from cogs.eat.views import EatBrowseView
import concurrent.futures
import asyncio

from typing import Optional
from .language_manager import LanguageManager
from llm.utils.send_message import safe_edit_message
from function import func
from addons.logging import get_logger

def install_driver():
    """Install Chrome driver using ChromeDriverManager."""
    return ChromeDriverManager().install()

class InternetSearchCog(commands.Cog):
    """Cog for internet search functionality including general web search, YouTube, and food recommendations."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = DB()
        self.recommender = WeightedRecommender(db=self.db)
        self.provider = get_restaurant_provider()
        self.lang_manager: Optional[LanguageManager] = None
        self.logger = get_logger(server_id="Bot", source="internet_search")

    async def cog_load(self):
        """Initialize LanguageManager when the cog is loaded."""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    async def cog_unload(self):
        """Close the restaurant provider's HTTP session when the cog is unloaded."""
        try:
            await self.provider.close()
        except Exception:
            pass

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
    async def search_command(self, interaction: discord.Interaction, type: Optional[app_commands.Choice[str]] = None, query: str = '') -> None:
        """Slash command wrapper for internet_search.
    
        Delegates to internet_search and returns the textual result if available.
        Ensures Discord message length limits are respected by splitting long
        markdown outputs into multiple followups.
        """
        await interaction.response.defer(thinking=True)
        selected_type = type.value if isinstance(type, app_commands.Choice) else (type or "general")
        guild_id = str(interaction.guild_id) if interaction.guild_id is not None else "0"
    
        def _split_markdown(md: str, limit: int = 1900) -> list:
            """Split markdown text into chunks not exceeding `limit` chars."""
            if not md:
                return []
            lines = md.splitlines(keepends=True)
            chunks = []
            cur = ""
            for ln in lines:
                if len(cur) + len(ln) > limit:
                    if cur:
                        chunks.append(cur)
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
                chunks = _split_markdown(result, limit=1900)
                try:
                    if not chunks:
                        await interaction.edit_original_response(content=result[:1900])
                    else:
                        await interaction.edit_original_response(content=chunks[0])
                        for chunk in chunks[1:]:
                            await interaction.followup.send(content=chunk)
                except Exception as send_err:
                    await func.report_error(send_err, f"search_command send followup failed: {send_err}")
                    try:
                        short = (result[:1900] + "...") if len(result) > 1900 else result
                        await interaction.edit_original_response(content=short)
                    except Exception:
                        pass
            else:
                # Cog handled messaging (embed/view).
                try:
                    if selected_type != "eat":
                        confirmation = self.lang_manager.translate(
                            guild_id,
                            "commands",
                            "internet_search",
                            "responses",
                            "search_complete",
                            query=query
                        ) if self.lang_manager else f"Search for '{query}' completed."
                        if len(confirmation) > 1900:
                            confirmation = confirmation[:1897] + "..."
                        await interaction.edit_original_response(content=confirmation)
                except Exception as notify_err:
                    await func.report_error(notify_err, f"search_command confirmation send failed: {notify_err}")
                    pass
        except Exception as e:
            is_blocked = "CAPTCHA triggered" in str(e) or "Google blocked the request" in str(e)
            if not is_blocked:
                await func.report_error(e, f"search_command: {e}")
            try:
                if is_blocked:
                    blocked_msg = self.lang_manager.translate(
                        guild_id, "commands", "internet_search", "errors", "blocked_by_google"
                    ) if self.lang_manager else "❌ 搜尋服務暫時不可用，請稍後再試。(Search service is temporarily unavailable, please try again later.)"
                    if blocked_msg.startswith("[Translation not found"):
                        blocked_msg = "❌ 搜尋服務暫時不可用，請稍後再試。(Search service is temporarily unavailable, please try again later.)"
                    await interaction.edit_original_response(content=blocked_msg)
                else:
                    await interaction.edit_original_response(content=f"Search failed: {e}")
            except Exception:
                pass

    async def internet_search(self, ctx, query: str, search_type: str = "general", message_to_edit: Optional[discord.Message] = None, guild_id: str = '0'):
        """High-level search entry point that delegates to specific search functions."""
        if message_to_edit:
            searching_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "internet_search",
                "responses",
                "searching"
            ) if self.lang_manager else "Searching..."
            try:
                await safe_edit_message(message_to_edit, searching_message)
            except discord.errors.NotFound:
                fallback_text = f"🔍 {searching_message}"
                try:
                    await ctx.channel.send(fallback_text)
                except Exception:
                    pass
                self.logger.info("Original message not found, sending new message instead.")
        
        normalized_type = (search_type or "").strip().lower()
        if normalized_type == "web":
            normalized_type = "general"
            self.logger.info("Received search_type='web', mapped to 'general'.")

        search_functions = {
            "general": self.google_search,
            "youtube": self.youtube_search,
            "eat": self.eat_search
        }
        
        search_func = search_functions.get(normalized_type)
        if search_func:
            if not guild_id or guild_id == '0':
                if isinstance(ctx, discord.Interaction):
                    guild_id = str(ctx.guild_id) if ctx.guild_id else "0"
                elif hasattr(ctx, 'guild') and ctx.guild:
                    guild_id = str(ctx.guild.id)
                
            result = await search_func(ctx, query, message_to_edit)
            return result if isinstance(result, str) else None
        else:
            self.logger.warning(f"Unknown search type: {search_type}")
            error_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "internet_search",
                "responses",
                "unknown_type",
                type=search_type
            ) if self.lang_manager else f"Unknown search type: {search_type}"
            return error_message

    async def google_search(self, ctx, query, message_to_edit=None):
        """Perform a web search using Gemini grounding, with fallback to legacy scraping."""
        guild_id = "0"
        if isinstance(ctx, discord.Interaction):
            guild_id = str(ctx.guild_id) if ctx.guild_id else "0"
        elif hasattr(ctx, 'guild') and ctx.guild:
            guild_id = str(ctx.guild.id)

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            err = RuntimeError("Gemini API key not found in environment")
            await func.report_error(err, "google_search: missing Gemini API key")
            return await self._legacy_google_search(ctx, query, message_to_edit)

        client = genai.Client(api_key=api_key)
        grounding_tool = types.Tool(google_search=types.GoogleSearch())

        # Localized system prompt for Gemini
        if self.lang_manager:
            system_prompt = self.lang_manager.translate(guild_id, "commands", "internet_search", "ai", "system_prompt")
            user_prefix = self.lang_manager.translate(guild_id, "commands", "internet_search", "ai", "user_query_prefix")
        else:
            system_prompt = "You are a web research agent. Synthesize a concise answer with highlights. Always respond in English."
            user_prefix = "User query: "

        contents = f"{system_prompt}\n\n{user_prefix}{query}"

        config = types.GenerateContentConfig(
            tools=[grounding_tool, {"url_context": {}}]
        )

        try:
            def call_gemini():
                return client.models.generate_content(
                    model=llm_config.google_search_agent,
                    contents=contents,
                    config=config
                )

            response = await asyncio.to_thread(call_gemini)

            if not response:
                raise RuntimeError("Failed to extract text from Gemini grounding response")

            result_text = str(response.text)
            
            # Extract grounding metadata and append sources
            sources_text = self._extract_sources_from_grounding(response)
            if sources_text:
                result_text += f"\n\n{sources_text}"
            
            return result_text

        except Exception as e:
            await func.report_error(e, f"google_search gemini grounding: {e}")
            return await self._legacy_google_search(ctx, query, message_to_edit)

    def _extract_sources_from_grounding(self, response):
        """Extract source URLs and titles from Gemini grounding metadata."""
        try:
            if not hasattr(response, 'candidates') or not response.candidates:
                return ""
            
            candidate = response.candidates[0]
            if not hasattr(candidate, 'grounding_metadata'):
                return ""
            
            grounding_metadata = candidate.grounding_metadata
            if not hasattr(grounding_metadata, 'grounding_chunks') or not grounding_metadata.grounding_chunks:
                return ""
            
            sources = []
            seen_urls = set()
            
            for chunk in grounding_metadata.grounding_chunks:
                if hasattr(chunk, 'web') and chunk.web:
                    uri = getattr(chunk.web, 'uri', None)
                    title = getattr(chunk.web, 'title', None)
                    
                    if uri and uri not in seen_urls:
                        seen_urls.add(uri)
                        display_text = title if title else uri
                        sources.append(f"- [{display_text}]({uri})")
            
            if not sources:
                return ""
            
            return "**Sources:**\n" + "\n".join(sources)
            
        except Exception as e:
            self.logger.warning(f"Failed to extract sources from grounding metadata: {e}")
            return ""

    async def _legacy_google_search(self, ctx, query, message_to_edit=None):
        """Original Selenium-based Google scraping preserved as a fallback."""
        chrome_options = self.get_chrome_options()

        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(install_driver)
                driver_path = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: future.result(timeout=10)
                )
                service = Service(driver_path)
        except Exception as e:
            self.logger.warning(f"ChromeDriverManager failed: {e}, falling back to local driver")
            chrome_driver_path = './chromedriverlinux64/chromedriver'
            service = Service(executable_path=chrome_driver_path)

        with webdriver.Chrome(options=chrome_options, service=service) as driver:
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                '''
            })

            url = f"https://www.google.com/search?q={query}"
            driver.get(url)
            time.sleep(random.uniform(1.5, 3.5))
            html = driver.page_source

        soup = BeautifulSoup(html, 'html.parser')
        search_results = soup.select('.g')
        search_results_with_links = []
        for result in search_results[:8]:
            title = result.select_one('h3').text if result.select_one('h3') else 'No Title'
            snippet = result.select_one('.VwiC3b').text if result.select_one('.VwiC3b') else 'No Snippet'
            link = result.select_one('a')['href'] if result.select_one('a') else 'No Link'
            search_results_with_links.append(f"{title}\n{snippet}\n{link}")

        search = "\n\n".join(search_results_with_links)
        if "Our systems have detected unusual traffic" in html:
            raise RuntimeError("Google blocked the request (CAPTCHA triggered)")
        return search

    @staticmethod
    def get_chrome_options():
        """Configure Chrome options for headless scraping."""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        return chrome_options

    async def youtube_search(self, ctx, query, message_to_edit=None):
        """Search for YouTube videos and return a random result from the top hits."""
        guild_id = "0"
        if isinstance(ctx, discord.Interaction):
            guild_id = str(ctx.guild_id) if ctx.guild_id else "0"
        elif hasattr(ctx, 'guild') and ctx.guild:
            guild_id = str(ctx.guild.id)

        try:
            results = YoutubeSearch(query, max_results=5).to_dict()
            if not results:
                return self.lang_manager.translate(
                    guild_id, "commands", "internet_search", "responses", "no_videos_found"
                ) if self.lang_manager else "No videos found."

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
            ) if self.lang_manager else f"Found: {selected_result['title']}"
            return video_description
        except Exception as e:
            await func.report_error(e, f"youtube_search: {e}")
            return self.lang_manager.translate(
                guild_id, "commands", "internet_search", "responses", "search_failed", error=str(e)
            ) if self.lang_manager else f"Search failed: {e}"

    async def eat_search(self, ctx, keyword: str = "_", message_to_edit: discord.Message = None):
        """Food recommendation search using WeightedRecommender and restaurant providers."""
        guild_id = "0"
        if isinstance(ctx, discord.Interaction):
            guild_id = str(ctx.guild_id) if ctx.guild_id else "0"
        elif hasattr(ctx, 'guild') and ctx.guild:
            guild_id = str(ctx.guild.id)

        # Step 1: Determine search keyword
        if keyword == "_":
            keywords_list = self.db.getKeywords()
            if not keywords_list:
                return self.lang_manager.translate(
                    guild_id, "commands", "internet_search", "errors", "eat_no_food"
                ) if self.lang_manager else "No food available"
            keyword = self.recommender.suggest_keyword(guild_id, [k[0] for k in keywords_list])
        else:
            if not self.db.checkKeyword(keyword=keyword):
                self.db.storeKeyword(keyword)

        # Step 2: Show loading embed
        loading = loadingEmbed(keyword, lang_manager=self.lang_manager, guild_id=guild_id)
        try:
            if isinstance(ctx, discord.Interaction):
                followup_msg = await ctx.followup.send(embed=loading)
            else:
                if message_to_edit:
                    try:
                        await message_to_edit.edit(embed=loading, view=None, content=None)
                        followup_msg = message_to_edit
                    except discord.errors.NotFound:
                        followup_msg = None
                else:
                    followup_msg = None
        except Exception:
            followup_msg = None

        try:
            # Step 3: Async search
            current_lang = self.lang_manager.get_server_lang(guild_id) if self.lang_manager else "en_US"
            
            if hasattr(self.provider, "async_search_list"):
                results = await self.provider.async_search_list(keyword, lang=current_lang)
            else:
                results = await self.provider.search(keyword, lang=current_lang)

            if not results:
                error_msg = self.lang_manager.translate(
                    guild_id, "commands", "internet_search", "errors", "eat_system_error",
                    keyword=keyword, error="No restaurants found"
                ) if self.lang_manager else f"No restaurants found for {keyword}"
                return error_msg

            # Step 4: Real-time fetch for the first result
            if not results[0].get("is_detailed", False) and hasattr(self.provider, "async_fetch_detail"):
                first_detail = await self.provider.async_fetch_detail(results[0].get("maps_url", ""), lang=current_lang)
                if first_detail:
                    results[0].update(first_detail)
                    results[0]["is_detailed"] = True

            # Step 5: Rank candidates
            ranked = self.recommender.rank_candidates(guild_id, results)
            if not ranked:
                ranked = results

            # Step 6: Store new tags
            first_place = ranked[0]
            tag = first_place.get("category", "")
            if tag and not self.db.checkKeyword(keyword=tag):
                self.db.storeKeyword(tag)

            # Step 7: Create View and Embed
            view = EatBrowseView(
                results=ranked,
                keyword=keyword,
                db=self.db,
                discord_id=guild_id,
                provider=self.provider,
                lang_manager=self.lang_manager,
                guild_id=guild_id
            )
            embed = browseEmbed(ranked, 0, lang_manager=self.lang_manager, guild_id=guild_id)

            # Step 8: Update message
            if isinstance(ctx, discord.Interaction):
                try:
                    await ctx.edit_original_response(embed=embed, view=view)
                except Exception:
                    await ctx.followup.send(embed=embed, view=view)
            else:
                if followup_msg:
                    try:
                        await followup_msg.edit(embed=embed, view=view, content=None)
                    except discord.errors.NotFound:
                        pass
            return None

        except Exception as e:
            await func.report_error(e, f"eat_search: {e}")
            return self.lang_manager.translate(
                guild_id, "commands", "internet_search", "errors", "eat_system_error",
                keyword=keyword, error=str(e)
            ) if self.lang_manager else f"Error: {e}"

async def setup(bot):
    """Set up the InternetSearchCog."""
    await bot.add_cog(InternetSearchCog(bot))
