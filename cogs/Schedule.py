import discord
import discord.app_commands as app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import pytz
import json
import re

weekday_map = {
    'Monday': '星期一',
    'Tuesday': '星期二',
    'Wednesday': '星期三',
    'Thursday': '星期四',
    'Friday': '星期五',
    'Saturday': '星期六',
    'Sunday': '星期日'
}


# 尋找下一節課的邏輯，考慮目前時間是第幾節課

class ScheduleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    def load_schedule_data(self, user_name):
        try:
            match = re.search(r'\d+', user_name)
            user_id = match.group()
            with open(f'./data/schedule_data/{user_id}.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        
    def find_next_class_corrected(self,schedule, weekday, current_class_period):
        print('目前是',weekday,'第',current_class_period,'節')
        if weekday not in schedule:
            return "今日無課程。"
        current_class_period = current_class_period if current_class_period > 0 else 0
        # 從目前節次開始搜尋下一節有安排的課
        for period in range(current_class_period, len(schedule[weekday])):
            if schedule[weekday][period]:  # 如果這個時間段有課
                class_info = schedule[weekday][period]
                
                return f"下一節課是第 {period + 1} 節 {period+8}:10開始，課名：{class_info['課名']}，教授：{class_info['教授']}，教室：{class_info['教室']}。"
        return "今日已無其他課程。"
    
    def find_current_class(self, schedule, weekday, current_class_period):
        print('目前是',weekday,'第',current_class_period,'節')
        if schedule is None:
            return "找不到課表數據。"
        
        if weekday not in schedule:
            return "今日無課程。"
        # 檢查目前時間對應的課程
        if schedule[weekday][current_class_period-1]:
            class_info = schedule[weekday][current_class_period-1]
            return f"目前是第 {current_class_period} 節，課名：{class_info['課名']}，教授：{class_info['教授']}，教室：{class_info['教室']}。"
        else:
            return "現在沒在上課。"
    
    @commands.hybrid_command(name="課表")
    @app_commands.describe(user_name="@用戶名稱，用於查詢特定用戶的課表")
    async def query_schedule(self, ctx, user_name: str = None):
        if user_name is None:
            user_name = f"<@{ctx.author.id}>"  # 若未提供ID，則使用命令發送者的ID
        schedule = self.load_schedule_data(str(user_name))
        if schedule is None:
            await ctx.send("找不到課表數據。")
            return
        # 獲取當前時間和星期
        tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tz)
        current_hour = now.hour
        current_weekday = now.strftime('%A')
        # 計算目前是第幾節課
        current_class_period = current_hour - 7  # 8點開始為第1節
        # 將英文星期轉換為中文
        current_weekday_cn = weekday_map.get(current_weekday, "")
        response = self.find_next_class_corrected(schedule, current_weekday_cn, current_class_period)
        await ctx.send(user_name+response)
        
    @commands.hybrid_command(name="正在上")
    @app_commands.describe(user_name="@用戶名稱，用於查詢特定用戶的現在課程")
    async def query_current_class(self, ctx, user_name: str = None):
        if user_name is None:
            user_name = f"<@{ctx.author.id}>"  # 若未提供ID，則使用命令發送者的ID
        schedule = self.load_schedule_data(str(user_name))
        if schedule is None:
            await ctx.send("找不到課表數據。")
            return
        # 獲取當前時間和星期
        tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tz)
        current_hour = now.hour
        current_weekday = now.strftime('%A')
        # 計算目前是第幾節課
        current_class_period = current_hour - 7  # 8點開始為第1節
        # 將英文星期轉換為中文
        current_weekday_cn = weekday_map.get(current_weekday, "")
        response = self.find_current_class(schedule, current_weekday_cn, current_class_period)
        await ctx.send(user_name+response)



async def setup(bot):
    await bot.add_cog(ScheduleCog(bot))
