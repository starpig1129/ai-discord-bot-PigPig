import os
import random
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
import threading
from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="eat.crawler")

# 定義一個用於從Google地圖爬取餐廳信息的類
class GoogleMapCrawler:
    def __init__(self):
        # 初始化 Chrome WebDriver 的選項
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--incognito")
        chrome_options.add_argument("--window-size=1920,1080")
        # 設定固定 User-Agent 避免被擋
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # 移除自動化控制標記
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        try:
            self.webdriver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        except Exception as e:
            logger.error(f"WebDriver 初始化失敗：{e}")
            # 備用方案：嘗試從本地路徑載入
            try:
                chrome_driver_path = './chromedriverlinux64/chromedriver'
                self.webdriver = webdriver.Chrome(service=Service(executable_path=chrome_driver_path), options=chrome_options)
            except Exception as e2:
                logger.error(f"本地 WebDriver 初始化也失敗：{e2}")
                raise e2
        
        # 建立執行緒鎖，確保 WebDriver 操作的安全
        self._lock = threading.Lock()
    
    def search(self, keyword: str, lang: str = "zh_TW"):
        """執行搜尋並抓取餐廳資訊。
        
        Args:
            keyword: 搜尋關鍵字。
            lang: 伺服器語言（zh_TW, zh_CN, en_US, ja_JP）。
        """
        # 語言與 Google Maps hl 參數及標籤的對照表
        lang_map = {
            "zh_TW": {"hl": "zh-TW", "menu": "菜單"},
            "zh_CN": {"hl": "zh-CN", "menu": "菜单"},
            "en_US": {"hl": "en", "menu": "Menu"},
            "ja_JP": {"hl": "ja", "menu": "メニュー"}
        }
        config = lang_map.get(lang, lang_map["zh_TW"])
        hl = config["hl"]
        menu_label = config["menu"]

        # 使用執行緒鎖保護共用的 WebDriver
        with self._lock:
            # 使用 hl 參數強制介面語言
            search_url = f"https://www.google.com/maps/search/{keyword}餐廳?hl={hl}"
            self.webdriver.get(search_url)
            url = search_url
            
            try:
                # 等待搜尋結果載入
                WebDriverWait(self.webdriver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "hfpxzc"))
                )
                html = self.webdriver.page_source
                soup = BeautifulSoup(html, "html.parser")
                self.url_all = soup.find_all("a", class_="hfpxzc")
                
                # 隨機選擇一個餐廳連結
                if self.url_all:
                    item = self.url_all[random.randint(0, len(self.url_all)-1)]
                    url = item.get('href', search_url)
                
                self.webdriver.get(url)
                # 等待餐廳頁面載入核心元素
                WebDriverWait(self.webdriver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "DUwDvf"))
                )
                html = self.webdriver.page_source
                selected = BeautifulSoup(html, "html.parser")
            except Exception as e:
                logger.warning(f"搜尋過程中斷或失敗：{e}")
                html = self.webdriver.page_source
                selected = BeautifulSoup(html, "html.parser")

            # 提取基本資訊
            title_el = selected.find('h1', class_='DUwDvf lfPIob')
            title = title_el.text.strip() if title_el else keyword
            rating_el = selected.find('span', class_='ceNzKf')
            rating = rating_el['aria-label'] if rating_el else '評分未知'
            category_el = selected.find('button', class_='DkEaL')
            category = category_el.text.strip() if category_el else '餐廳'
            address_el = selected.find('button', class_='CsEnBe')
            address = address_el['aria-label'] if address_el else '地址未提供'
            
            viewelements = selected.find_all(class_='DUGVrf')
            
            # 抓取評論部分（略過詳細滾動邏輯以維持穩定性，除非必要）
            try:
                # 嘗試簡單滾動一次以觸發載入
                self.webdriver.execute_script("window.scrollBy(0, 500);")
                sleep(0.5)
            except:
                pass

            pattern = re.compile(r'撰寫「"(.+?)"」的評論者相片')
            reviews = [pattern.search(str(el)).group(1) for el in viewelements if pattern.search(str(el))]
            
            # 嘗試抓取菜單
            menu = '無法取得菜單'
            try:
                # 嘗試找到進入菜單的按鈕
                menu_btn_xpath = [
                    f"//button[@role='tab' and contains(@aria-label, '{menu_label}')]",
                    f"//div[@role='tab' and contains(@aria-label, '{menu_label}')]",
                    f"//button[contains(@aria-label, '{menu_label}')]"
                ]
                
                button = None
                for xpath in menu_btn_xpath:
                    try:
                        button = WebDriverWait(self.webdriver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, xpath))
                        )
                        if button: break
                    except:
                        continue
                
                if not button:
                    # 如果找不到標籤按鈕，嘗試點擊包含「菜單」字樣的任何按鈕
                    try:
                        button = WebDriverWait(self.webdriver, 2).until(
                            EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{menu_label}')]/ancestor-or-self::button"))
                        )
                    except:
                        button = None
                
                if button:
                    button.click()
                    # 確保我們抓的是「菜單」相簿裡的第一張實體菜單圖片（排除用戶頭像等小圖）
                    sleep(2)  # 等待相簿介面動畫
                    try:
                        menu_img_el = WebDriverWait(self.webdriver, 5).until(
                            EC.presence_of_element_located((
                                By.XPATH, 
                                f"//div[contains(@aria-label, '{menu_label}')]//button[contains(@aria-label, '第 1 張') or contains(@aria-label, 'Photo 1')]//img"
                            ))
                        )
                        
                        img_url = menu_img_el.get_attribute('src')

                        if img_url:
                            # 轉換為高解析度
                            if '=' in img_url:
                                img_url = img_url.split('=')[0] + '=s1536'
                            menu = img_url
                    except Exception as img_err:
                        # 備案：排除明顯的頭像尺寸 (s32, s64, s120)，抓取較大張的 google 圖片
                        try:
                            fallback_img_el = WebDriverWait(self.webdriver, 3).until(
                                EC.presence_of_element_located((
                                    By.XPATH, 
                                    "//div[contains(@aria-label, '菜單') or contains(@aria-label, 'Menu')]//img[contains(@src, 'googleusercontent') and not(contains(@src, 's120')) and not(contains(@src, 's64')) and not(contains(@src, 'p-k-no-mo'))]"
                                ))
                            )
                            img_url = fallback_img_el.get_attribute('src')
                            if img_url:
                                if '=' in img_url:
                                    img_url = img_url.split('=')[0] + '=s1536'
                                menu = img_url
                        except:
                            logger.warning(f"找圖片失敗: {img_err}")
                else:
                    logger.warning("找不到菜單按鈕")
            except Exception as e:
                logger.warning(f"get_menu 外層失敗：{e}")
            
            # 返回爬取到的數據
            return (title, rating, category, address, url, str(reviews), menu)
    
    async def async_search(self, keyword: str, lang: str = "zh_TW") -> list:
        """非同步包裝器。
        
        Args:
            keyword: 搜尋關鍵字。
            lang: 語系代碼。
        """
        loop = asyncio.get_running_loop()
        try:
            result_tuple = await loop.run_in_executor(None, self.search, keyword, lang)
        except Exception as e:
            logger.error(f"async_search 失敗：{e}")
            return []
        (title, rating, category, address, url, reviews, menu) = result_tuple
        # 解析 rating 字串為 float（例：「4.2 顆星」→ 4.2）
        try:
            parsed_rating = float(re.search(r'[\d.]+', rating).group())
        except Exception:
            parsed_rating = 0.0
        return [{
            "place_id": "",
            "name": title,
            "rating": parsed_rating,
            "category": category,
            "address": address,
            "maps_url": url,
            "photo_url": menu if menu != "無法取得菜單" else "",
            "reviews": [],
            "price_level": 0,
            "opening_hours": [],
            "phone": "",
        }]

    def close(self):
        self.webdriver.close()  # 關閉webdriver
