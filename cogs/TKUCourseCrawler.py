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
import discord.app_commands as app_commands
from discord.ext import commands
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import time
import json


class TKUCourseCrawler:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # 無頭
        chrome_options.add_argument("--no-sandbox")  # 禁用沙盒模式
        chrome_options.add_argument("--disable-dev-shm-usage")  
        s = Service('./chromedriver-linux64/chromedriver')  # 指定chromedriver的路径
        self.driver = webdriver.Chrome(options=chrome_options, service=s)

    def login(self):
        login_url = "https://sso.tku.edu.tw/NEAI/logineb.jsp?myurl=https://sso.tku.edu.tw/aissinfo/emis/TMW0000.aspx"
        self.driver.get(login_url)
        WebDriverWait(self.driver, 1).until(EC.presence_of_element_located((By.NAME, "username")))
        self.driver.find_element(By.NAME, "username").send_keys(self.username)
        self.driver.find_element(By.NAME, "password").send_keys(self.password)
        self.driver.find_element(By.NAME, "loginbtn").click()

    def navigate_to_courses_page(self):
        WebDriverWait(self.driver, 2).until(EC.presence_of_element_located((By.LINK_TEXT, "選課資料(依上課星期、節次列表)")))
        self.driver.find_element(By.LINK_TEXT, "選課資料(依上課星期、節次列表)").click()
        self.driver.find_element(By.LINK_TEXT, "查詢選課/考試資料(依上課星期、節次列表)").click()
    def extract_courses(self):
        # 确保页面已加载
        WebDriverWait(self.driver, 1).until(EC.presence_of_element_located((By.NAME, "Button1")))
        self.driver.find_element(By.NAME, "Button1").click()
        time.sleep(1)  # 等待数据加载完成

        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        schedule = {day: [] for day in weekdays}
        courses = self.driver.find_elements(By.XPATH, '//td[contains(@class, "line-right line-top btd-")]')
        n = 0
        for course_slot in courses:
            if n == 0:
                n+=1
                continue
            elif n == 8:
                n = 0
            course_name = course_slot.find_element(By.XPATH, ".//a").text.strip() if course_slot.find_elements(By.XPATH, ".//a") else ""
            teacher_and_room = course_slot.text.split('\n')[-1]
            # 分割字符串以提取教師名稱和教室號碼
            teacher_and_room_parts = teacher_and_room.split('_')
            if len(teacher_and_room_parts) >= 2:
                teacher = teacher_and_room_parts[0].strip()
                room = teacher_and_room_parts[1].strip()
            else:
                teacher = ""
                room = ""
            #助教課課名
            if teacher == "助　教":
                course_name = course_slot.text.split('\n')[-2]
            if course_name == "":
                schedule[weekdays[n-1]].append({})    
            else:    
                schedule[weekdays[n-1]].append({
                    "課名": course_name,  # 課程名稱
                    "教授": teacher,  # 教師名稱
                    "教室": room.replace(" ",""),  # 教室號碼
                })
            n+=1
        schedule = {day: schedule[day][1:] for day in weekdays}#去除第一排
        schedule["星期日"] = schedule["星期日"][:14]
        return schedule
    def save_courses_to_json(self, courses, file_path='courses.json'):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(courses, f, ensure_ascii=False, indent=4)
            print(f"課程訊息已保存到 {file_path}")
    def close(self):
        self.driver.quit()
        
class DiscordBotCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def run_crawler(self,dcid, username, password):
        crawler = TKUCourseCrawler(username, password)
        crawler.login()
        crawler.navigate_to_courses_page()
        courses = crawler.extract_courses()
        crawler.save_courses_to_json(courses,file_path=f'./data/schedule_data/{dcid}.json')
        crawler.close()
        return courses
        
    @commands.hybrid_command(name="建立課表")
    @app_commands.describe(username="用戶名稱，學號",password="淡江單一登入密碼")
    async def get_courses(self,ctx, username: str, password: str):
        try:
            await ctx.send('課表資訊建立中', ephemeral=True)
            await self.bot.loop.run_in_executor(None, self.run_crawler,str(ctx.author.id), username, password)
            await ctx.send('課表資訊建立完成!', ephemeral=True)
        except Exception as e:
            await ctx.send('無法獲取課程資訊。', ephemeral=True)
async def setup(bot):
    await bot.add_cog(DiscordBotCog(bot))
