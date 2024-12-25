import os
import asyncio
import logging as logger

# 定義每個伺服器的播放清單
guild_queues = {}

def get_guild_queue_and_folder(guild_id):
    """確保伺服器有獨立的資料夾和播放清單"""
    if guild_id not in guild_queues:
        guild_queues[guild_id] = asyncio.Queue()

    # 為每個伺服器設定獨立的下載資料夾
    guild_folder = f"./temp/music/{guild_id}"
    if not os.path.exists(guild_folder):
        os.makedirs(guild_folder)
    return guild_queues[guild_id], guild_folder

def clear_guild_queue(guild_id):
    """清空指定伺服器的播放清單"""
    if guild_id in guild_queues:
        guild_queues[guild_id] = asyncio.Queue()

async def copy_queue(guild_id):
    """複製隊列內容而不消耗原隊列"""
    queue = guild_queues.get(guild_id)
    if not queue:
        return [], asyncio.Queue()
        
    queue_copy = []
    temp_queue = asyncio.Queue()
    while not queue.empty():
        item = await queue.get()
        queue_copy.append(item)
        await temp_queue.put(item)
    guild_queues[guild_id] = temp_queue
    
    return queue_copy, temp_queue
