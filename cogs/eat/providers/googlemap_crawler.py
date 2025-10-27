import os
import random
import logging
import platform
from time import sleep
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re
import concurrent.futures
import asyncio
import function as func

logger = logging.getLogger(__name__)

# 定義一個用於從Google地圖爬取餐廳信息的類
class GoogleMapCrawler:
    def __init__(self):
        # 初始化Chrome WebDriver的選項
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # 啟用無頭模式，不顯示瀏覽器界面
        chrome_options.add_argument("--disable-gpu")  # 禁用GPU加速
        chrome_options.add_argument("--incognito")  # 啟用無痕模式

        self.webdriver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    def search(self, keyword):
        # 使用webdriver打開特定的Google地圖搜索URL
        self.webdriver.get(f"https://www.google.com/maps/search/{keyword}餐廳")
        html = self.webdriver.page_source
        soup = BeautifulSoup(html, "html.parser")
        try:
            # 尋找所有含餐廳連結的<a>標籤
            self.url_all = soup.find_all("a", class_="hfpxzc")
            # 隨機選擇一個餐廳連結
            url = self.url_all[round(random.randint(0, len(self.url_all)-1))]['href']
            self.webdriver.get(url)
        
            html = self.webdriver.page_source
            selected = BeautifulSoup(html, "lxml")
        except Exception as e:
            asyncio.create_task(func.func.report_error(e, "cogs/eat/providers/googlemap_crawler.py/search/get_url"))
            print('只有一個結果')
            url=f"https://www.google.com/maps/search/{keyword}餐廳"
            selected = BeautifulSoup(html, "lxml")
        # 提取餐廳的標題、評分、類別和地址
        title = selected.find('h1', class_='DUwDvf lfPIob').text.strip()
        rating = selected.find('span', class_='ceNzKf')['aria-label']
        category = selected.find('button', class_='DkEaL').text.strip()
        address = selected.find('button', class_='CsEnBe')['aria-label']
        viewelements = selected.find_all(class_='DUGVrf')
        old_page = None
        max_retries = 2  # 最大重試次數
        retries = 0
        try:
            while retries < max_retries and old_page != self.webdriver.page_source:
                old_page = self.webdriver.page_source
                element = WebDriverWait(self.webdriver, 1).until(
                    EC.visibility_of_element_located((By.CLASS_NAME, "zSdcRe "))  
                )
                self.webdriver.execute_script("arguments[0].scrollIntoView(true);", element)
                retries += 1   
        except Exception as e:
            asyncio.create_task(func.func.report_error(e, "cogs/eat/providers/googlemap_crawler.py/search/get_reviews"))
            reviews='撰寫「找不到評論」的評論者相片'
        # 使用正則表達式提取評論
        pattern = re.compile(r'撰寫「"(.+?)"」的評論者相片')
        reviews = [pattern.search(str(el)).group(1) if pattern.search(str(el)) else 'No match' for el in viewelements]
        #嘗試抓取菜單
        try:
            button = WebDriverWait(self.webdriver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.K4UgGe[aria-label="菜單"]'))
            )
            button.click()
            element = WebDriverWait(self.webdriver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, 'div.U39Pmb[role="img"]'))
            )
            style_attribute = element.get_attribute('style')
            url_start = style_attribute.find("url(\"") + len("url(\"")
            url_end = style_attribute.find("&quot;)", url_start)
            menu = style_attribute[url_start:url_end]
            equal_index = menu.find('=')
            menu = menu[:equal_index]+'=s1536'
        except Exception as e:
            asyncio.create_task(func.func.report_error(e, "cogs/eat/providers/googlemap_crawler.py/search/get_menu"))
            menu = '無法取得菜單'
        sleep(1)
        # 返回爬取到的所有數據
        return (title, rating, category, address, url, str(reviews), menu)
    
    def close(self):
        self.webdriver.close()  # 關閉webdriver
