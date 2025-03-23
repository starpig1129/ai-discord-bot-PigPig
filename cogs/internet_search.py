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
import aiohttp
import re
import requests
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
import cv2
import glob
from skimage.metrics import structural_similarity as ssim

from cogs.eat.db.db import DB
from cogs.eat.embeds import eatEmbed
from cogs.eat.providers.googlemap_crawler import GoogleMapCrawler
from cogs.eat.train.train import Train
from cogs.eat.views import EatWhatView

class InternetSearchCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DB()
        self.train = Train(db=self.db)
        self.map = GoogleMapCrawler()

    @app_commands.command(name="internet_search", description="進行網絡搜索")
    @app_commands.choices(search_type=[
        app_commands.Choice(name="一般搜索", value="general"),
        app_commands.Choice(name="圖片搜索", value="image"),
        app_commands.Choice(name="YouTube搜索", value="youtube"),
        app_commands.Choice(name="網址內容", value="url"),
        app_commands.Choice(name="吃什麼", value="eat")
    ])
    async def search_command(self, interaction: discord.Interaction, query: str, search_type: str):
        await interaction.response.defer(thinking=True)
        result = await self.internet_search(interaction, query, search_type)
        if result is not None:
            await interaction.followup.send(result)
            
    async def internet_search(self, ctx, query: str, search_type: str, message_to_edit: discord.Message = None):
        if message_to_edit:
            await message_to_edit.edit(content="尋找中...")
        
        search_functions = {
            "general": self.google_search,
            "image": self.send_img,
            "youtube": self.youtube_search,
            "url": self.fetch_page_content,
            "eat": self.eat_search
        }
        
        search_func = search_functions.get(search_type)
        if search_func:
            result = await search_func(ctx, query, message_to_edit)
            return result if isinstance(result, str) else None
        else:
            return f"未知的搜索類型: {search_type}"

    async def google_search(self, ctx, query, message_to_edit=None):
        chrome_options = self.get_chrome_options()
        service = Service(ChromeDriverManager().install())
        
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

    async def send_img(self, ctx, query, message_to_edit):
        print('圖片搜尋:', query)

        url = f"https://www.google.com.hk/search?q={query}&tbm=isch"
        chrome_options = self.get_chrome_options()
        service = Service(ChromeDriverManager().install())

        try:
            with webdriver.Chrome(options=chrome_options, service=service) as driver:
                driver.get(url)
                driver.maximize_window()
                time.sleep(2)

                image_elements = driver.find_elements(By.CLASS_NAME, 'ob5Hkd')
                chosen_element = self.choose_random_element(image_elements)
                chosen_element.click()

                time.sleep(2)
                smail_pic_elements = driver.find_elements(By.CLASS_NAME, 'sFlh5c.pT0Scc')
                goto_url_elements = driver.find_elements(By.CLASS_NAME, 'umNKYc')

                if len(smail_pic_elements) > 1 and len(goto_url_elements) > 1:
                    smail_pic = smail_pic_elements[1]
                    goto_url_elements[1].click()
                elif len(smail_pic_elements) > 0 and len(goto_url_elements) > 0:
                    smail_pic = smail_pic_elements[0]
                    goto_url_elements[0].click()
                else:
                    raise Exception("無法找到圖片元素或跳轉URL元素")

                src = smail_pic.get_attribute('src')
                self.save_image('./gpt/img/need.jpg', src)

                time.sleep(1)
                driver.switch_to.window(driver.window_handles[-1])

                all_img = driver.find_elements(By.TAG_NAME, 'img')
                for idx, img in enumerate(all_img):
                    try:
                        img_url = img.get_attribute('src')
                        self.save_image(f'./gpt/img/image_{idx}.jpg', img_url)
                    except:
                        pass

            self.process_images(ctx, message_to_edit)

        except Exception as e:
            print(f"圖片下載失敗: {e}")
            self.send_error_message(ctx, message_to_edit, "圖片下載失敗")

        return None

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
    def choose_random_element(elements):
        base_weight = 1.5
        weights = [base_weight ** i for i in range(len(elements))]
        total_weight = sum(weights)
        probabilities = [weight / total_weight for weight in weights]
        return random.choices(elements, weights=probabilities)[0]

    @staticmethod
    def save_image(filename, url):
        with open(filename, 'wb') as f:
            f.write(requests.get(url).content)

    async def process_images(self, ctx, message_to_edit):
        need = cv2.imread('./gpt/img/need.jpg', cv2.IMREAD_GRAYSCALE)
        directory = './gpt/img/'
        jpg_files = glob.glob(os.path.join(directory, '*.jpg'))

        similarity_dict = {}
        for jpg_file in jpg_files:
            if "need" not in jpg_file:
                img2 = cv2.imread(jpg_file, cv2.IMREAD_GRAYSCALE)
                try:
                    img2 = cv2.resize(img2, (need.shape[1], need.shape[0]))
                    ssim_value, _ = ssim(need, img2, full=True)
                    similarity_dict[jpg_file] = ssim_value
                except:
                    pass

        max_file = max(similarity_dict, key=similarity_dict.get)
        with open(max_file, 'rb') as file:
            picture = discord.File(file, filename='./gpt/image.jpg')
            if isinstance(ctx, discord.Interaction):
                await ctx.followup.send(file=picture)
            else:
                await message_to_edit.edit(file=picture)

        for file in os.listdir(directory):
            if file.endswith('.jpg'):
                os.remove(os.path.join(directory, file))

    @staticmethod
    async def send_error_message(ctx, message_to_edit, content):
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(content=content)
        else:
            await message_to_edit.edit(content=content)

    async def youtube_search(self, ctx, query, message_to_edit=None):
        try:
            results = YoutubeSearch(query, max_results=5).to_dict()
            if not results:
                return "未找到相關影片，請嘗試其他關鍵詞。"

            selected_result = random.choice(results)
            video_description = (
                f"YoutubeSearch的結果：\n"
                f"標題: {selected_result['title']}\n"
                f"發布者: {selected_result['channel']}\n"
                f"觀看次數: {selected_result['views']}\n"
                f"連結: https://www.youtube.com{selected_result['url_suffix']}"
            )
            return video_description
        except Exception as e:
            return f"搜尋失敗，請換一下關鍵詞。錯誤：{str(e)}"

    async def fetch_page_content(self, ctx, query=None, message_to_edit=None):
        url_regex = r'(https?://\S+)'
        if isinstance(ctx, discord.Interaction):
            content = ctx.data.get('options', [{}])[0].get('value', '')
        else:
            content = ctx.content
        urls = re.findall(url_regex, content)
        if not urls:
            return "未找到有效的URL"
        
        all_texts = []
        error_messages = []
        
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            body_content = soup.body
                            if body_content:
                                for element in body_content(['header', 'footer', 'nav', 'aside', 'form', 'button', 'script', 'style']):
                                    element.decompose()
                                text = body_content.get_text(separator='\n', strip=True)
                                all_texts.append(text)
                            else:
                                error_messages.append(f"Failed to find body content in {url}")
                        else:
                            error_messages.append(f"Failed to fetch page content from {url}, status code: {response.status}")
                except Exception as e:
                    error_messages.append(f"Error while fetching {url}: {str(e)}")
        
        combined_text = "\n\n".join(all_texts)
        combined_errors = "\n".join(error_messages)
        
        result = combined_text if combined_text else "未能抓取到任何有效内容"
        if combined_errors:
            result += f"\n\nErrors:\n{combined_errors}"
        
        return result

    async def eat_search(self, ctx, keyword: str = "_", message_to_edit: discord.Message = None):
        predict = None
        if keyword == "_":
            keywords_list = self.db.getKeywords()
            if len(keywords_list) == 0:
                return "沒有這種食物喔"
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
                await message_to_edit.edit(embed=embed, view=view)

            self.train.genModel(str(ctx.guild.id))
            return None  
        except Exception as e:
            return f"原本想推薦你吃 {keyword if predict is None else predict}，但很抱歉系統出錯了QQ: {str(e)}"

async def setup(bot):
    await bot.add_cog(InternetSearchCog(bot))