import discord
import asyncio
from datetime import datetime, timedelta, timezone
import re

async def send_reminder(message_to_edit, message, user_name: str = None, reminder_message = None, time_str = None):
    await message_to_edit.edit(content="收到提醒")
    print(time_str)
    print(reminder_message)
    try:
        # 确定提醒时间
        reminder_time = None
        current_time = datetime.now()

        # 解析多久后提醒
        time_match = re.match(r'(\d+)(秒|分鐘|小時|天)後', time_str)
        if time_match:
            amount = int(time_match.group(1))
            unit = time_match.group(2)
            if unit == '秒':
                reminder_time = current_time + timedelta(seconds=amount)
            elif unit == '分鐘':
                reminder_time = current_time + timedelta(minutes=amount)
            elif unit == '小時':
                reminder_time = current_time + timedelta(hours=amount)
            elif unit == '天':
                reminder_time = current_time + timedelta(days=amount)
        else:
            # 解析指定时间提醒
            try:
                reminder_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                reminder_time = datetime.strptime(time_str, '%Y年%m月%d日%H:%M:%S')

        if user_name is None:
            user_name = message.author.id

        # 計算差異
        time_diff = reminder_time - current_time
        print(str(time_diff))
        if time_diff.total_seconds() > 0:
            await message_to_edit.edit(content=f"將在 {str(time_diff)[:-7]} 後傳送給 {user_name}")
            await asyncio.sleep(time_diff.total_seconds())
        await message.channel.send(f"{user_name} {reminder_message}")
        print(f"已成功傳送提醒給 Discord ID: {user_name}")
    except discord.errors.NotFound:
        print(f"找不到 Discord ID 為 {user_name} 的用户")
    except discord.errors.Forbidden:
        print(f"無權限傳送訊息給 {user_name}")
    except Exception as e:
        print(f"傳送提醒時發生錯誤:{str(e)}")
