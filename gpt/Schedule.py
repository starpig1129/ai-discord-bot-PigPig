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
def load_schedule_data(user_name,message):
    try:
        match = re.search(r'\d+', user_name)
        user_id = match.group()
        with open(f'./data/schedule_data/{user_id}.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        user_id = message.author.id
        with open(f'./data/schedule_data/{user_id}.json', 'r', encoding='utf-8') as f:
            return json.load(f)
def find_next_class_corrected(schedule, weekday, current_class_period):
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

def find_current_class(schedule, weekday, current_class_period):
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
async def query_schedule(message_to_edit, message,user_name:str=None,query_type:str='next'):
    await message_to_edit.edit(content="看看課表")
    try:
        if user_name is None:
            user_name = f"<@{message.author.id}>"  # 若未提供ID，則使用命令發送者的ID
        schedule = load_schedule_data(str(user_name),message)
        if schedule is None:
            return "找不到課表數據。"
        # 獲取當前時間和星期
        tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tz)
        current_hour = now.hour
        current_weekday = now.strftime('%A')
        # 計算目前是第幾節課
        current_class_period = current_hour - 7  # 8點開始為第1節
        # 將英文星期轉換為中文
        current_weekday_cn = weekday_map.get(current_weekday, "")
        if query_type == 'next':
            return 'user'+user_name +'的課表為'+ find_next_class_corrected(schedule, current_weekday_cn, current_class_period)
        if query_type == 'now':   
            return 'user'+user_name +'的課表為'+ find_current_class(schedule, current_weekday_cn, current_class_period)
        else:
            return '沒有資訊'
    except Exception as e:
        print('query_schedule:',e)