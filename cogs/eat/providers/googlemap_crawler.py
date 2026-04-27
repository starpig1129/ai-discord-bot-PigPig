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

class GoogleMapCrawler:
    def __init__(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--incognito")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        try:
            self.webdriver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        except Exception as e:
            logger.error(f"WebDriver 初始化失敗：{e}")
            try:
                chrome_driver_path = './chromedriverlinux64/chromedriver'
                self.webdriver = webdriver.Chrome(service=Service(executable_path=chrome_driver_path), options=chrome_options)
            except Exception as e2:
                logger.error(f"本地 WebDriver 初始化也失敗：{e2}")
                raise e2
        
        self._lock = threading.Lock()

    def search_list(self, keyword: str, lang: str = "zh_TW") -> list[dict]:
        """快速爬取搜尋結果列表。
        
        Returns:
            list[dict]: 包含 name, maps_url 的初步字典列表。
        """
        lang_map = {"zh_TW": "zh-TW", "zh_CN": "zh-CN", "en_US": "en", "ja_JP": "ja"}
        hl = lang_map.get(lang, "zh-TW")

        with self._lock:
            search_url = f"https://www.google.com/maps/search/{keyword}餐廳?hl={hl}"
            self.webdriver.get(search_url)
            
            try:
                WebDriverWait(self.webdriver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "hfpxzc"))
                )
                
                # 執行滾動以載入更多結果
                try:
                    # 搜尋結果的滾動容器
                    scrollable_div = self.webdriver.find_element(By.XPATH, "//div[contains(@role, 'feed')]")
                    for _ in range(3):
                        self.webdriver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scrollable_div)
                        sleep(1.0)
                except Exception as scroll_err:
                    logger.warning(f"滾動失敗（可能不需要滾動）: {scroll_err}")

                html = self.webdriver.page_source
                soup = BeautifulSoup(html, "html.parser")
                
                # 取得所有搜尋結果元素
                cards = soup.find_all("a", class_="hfpxzc")
                results = []
                for card in cards[:40]: # 增加到 40 筆
                    name = card.get('aria-label', "未知餐廳")
                    link = card.get('href', "")
                    if name and link:
                        results.append({
                            "name": name,
                            "maps_url": link,
                            "is_detailed": False
                        })
                
                logger.info(f"「{keyword}」搜尋清單抓取完成，共 {len(results)} 筆結果。")
                return results
            except Exception as e:
                logger.warning(f"search_list 失敗：{e}")
                return []

    def fetch_detail(self, url: str, lang: str = "zh_TW") -> dict:
        """導航至特定餐廳頁面，抓取詳盡資訊（地址、評分、照片等）。"""
        lang_map = {
            "zh_TW": {"hl": "zh-TW", "menu": "菜單"},
            "zh_CN": {"hl": "zh-CN", "menu": "菜单"},
            "en_US": {"hl": "en", "menu": "Menu"},
            "ja_JP": {"hl": "ja", "menu": "メニュー"}
        }
        config = lang_map.get(lang, lang_map["zh_TW"])
        hl = config["hl"]
        menu_label = config["menu"]

        with self._lock:
            if not url.startswith("http"):
                return {}
            
            # 確保語系正確
            fixed_url = url
            if "hl=" not in fixed_url:
                fixed_url += f"&hl={hl}" if "?" in fixed_url else f"?hl={hl}"
            
            self.webdriver.get(fixed_url)
            try:
                # 等待關鍵元件載入
                WebDriverWait(self.webdriver, 12).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "DUwDvf"))
                )
                html = self.webdriver.page_source
                selected = BeautifulSoup(html, "html.parser")

                # 提取基本資訊
                title_el = selected.find('h1', class_='DUwDvf lfPIob')
                title = title_el.text.strip() if title_el else "未知"
                
                rating_el = selected.find('span', class_='ceNzKf')
                rating_str = rating_el['aria-label'] if rating_el else '0.0'
                try:
                    rating = float(re.search(r'[\d.]+', rating_str).group())
                except:
                    rating = 0.0

                category_el = selected.find('button', class_='DkEaL')
                category = category_el.text.strip() if category_el else '餐廳'
                
                # 地址：
                address = "地址未提供"
                address_candidates = [
                    selected.find('button', class_='CsEnBe'),
                    selected.find('div', class_='Io6YTe fontBodyMedium kR99Oc'),
                    selected.find('div', class_='R6vSre')
                ]
                for cand in address_candidates:
                    if cand and cand.get('aria-label'):
                        address = cand['aria-label'].replace('地址: ', '').strip()
                        break
                    elif cand and cand.text:
                        text = cand.text.strip()
                        if text and len(text) > 5:
                            address = text
                            break
                address = address.replace('地址: ', '')

                # 菜單圖片 (Menu) - 恢復強大邏輯
                menu = ""
                try:
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
                        try:
                            button = WebDriverWait(self.webdriver, 2).until(
                                EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{menu_label}')]/ancestor-or-self::button"))
                            )
                        except:
                            button = None
                    
                    if button:
                        button.click()
                        sleep(2)
                        try:
                            # 嘗試抓取第一張或符合條件的圖片
                            img_el = WebDriverWait(self.webdriver, 5).until(
                                EC.presence_of_element_located((
                                    By.XPATH, 
                                    f"//div[contains(@aria-label, '{menu_label}') or contains(@aria-label, 'Menu')]//img[contains(@src, 'googleusercontent') and not(contains(@src, 's120')) and not(contains(@src, 's64')) and not(contains(@src, 'p-k-no-mo'))]"
                                ))
                            )
                            img_url = img_el.get_attribute('src')
                            if img_url:
                                menu = img_url.split('=')[0] + '=s1536'
                        except:
                            pass
                except Exception as menu_err:
                    logger.warning(f"菜單抓取細節失敗: {menu_err}")

                return {
                    "name": title,
                    "rating": rating,
                    "category": category,
                    "address": address,
                    "maps_url": url,
                    "photo_url": menu,
                    "is_detailed": True
                }
            except Exception as e:
                logger.warning(f"fetch_detail 失敗 ({url}): {e}")
                return {
                    "name": "無法抓取",
                    "rating": 0.0,
                    "category": "餐廳",
                    "address": "連線逾時",
                    "maps_url": url,
                    "photo_url": "",
                    "is_detailed": True
                }

    async def async_search_list(self, keyword: str, lang: str = "zh_TW") -> list[dict]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.search_list, keyword, lang)

    async def async_fetch_detail(self, url: str, lang: str = "zh_TW") -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.fetch_detail, url, lang)

    def close(self):
        try:
            self._lock.acquire()
            self.webdriver.quit()
        except:
            pass
        finally:
            if self._lock.locked():
                self._lock.release()
