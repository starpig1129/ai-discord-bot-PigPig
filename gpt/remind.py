import discord
import asyncio
from datetime import datetime, timezone

async def send_reminder(message_to_edit, message, user_name: str = None, reminder_message = None, time_str = None):
    await message_to_edit.edit(content="收到提醒")
    try:
        # 解析提醒時間，支援多種格式
        try:
            reminder_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            reminder_time = datetime.strptime(time_str, '%Y年%m月%d日%H:%M:%S')
        if user_name is None:
            user_name = message.author.id
        
        # 使用當前時間
        message_time = datetime.now()
        
        # 將提醒時間設置為與當前時間同一時區
        reminder_time = reminder_time.replace(tzinfo=message_time.tzinfo)
        
        # 計算提醒時間與當前時間的差異
        time_diff = reminder_time - message_time
        
        if time_diff.total_seconds() > 0:
            await message_to_edit.edit(content=f"將在 {str(time_diff)[:-7]} 後傳送提醒給 {user_name}")
            await asyncio.sleep(time_diff.total_seconds())
        await message.channel.send(f"{user_name} {reminder_message}")
        print(f"已成功傳送提醒給 Discord ID: {user_name}")
    except discord.errors.NotFound:
        print(f"找不到 Discord ID 為 {user_name} 的使用者")
    except discord.errors.Forbidden:
        print(f"無權限傳送訊息給 {user_name}")
    except Exception as e:
        print(f"傳送提醒時發生錯誤：{str(e)}")

