import os
import asyncio
import random
import logging as logger

# 定義每個伺服器的播放清單和設置
guild_queues = {}
guild_settings = {}

class PlayMode:
    NO_LOOP = "no_loop"
    LOOP_QUEUE = "loop_queue"
    LOOP_SINGLE = "loop_single"

def get_guild_settings(guild_id):
    """獲取伺服器的播放設置"""
    if guild_id not in guild_settings:
        guild_settings[guild_id] = {
            "play_mode": PlayMode.NO_LOOP,
            "shuffle": False
        }
    return guild_settings[guild_id]

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
    if guild_id in guild_settings:
        guild_settings[guild_id]["play_mode"] = PlayMode.NO_LOOP
        guild_settings[guild_id]["shuffle"] = False

def toggle_shuffle(guild_id):
    """切換隨機播放狀態"""
    settings = get_guild_settings(guild_id)
    settings["shuffle"] = not settings["shuffle"]
    return settings["shuffle"]

def set_play_mode(guild_id, mode):
    """設置播放模式"""
    if mode in [PlayMode.NO_LOOP, PlayMode.LOOP_QUEUE, PlayMode.LOOP_SINGLE]:
        settings = get_guild_settings(guild_id)
        settings["play_mode"] = mode
        return True
    return False

def get_play_mode(guild_id):
    """獲取播放模式"""
    settings = get_guild_settings(guild_id)
    return settings["play_mode"]

def is_shuffle_enabled(guild_id):
    """檢查是否啟用隨機播放"""
    settings = get_guild_settings(guild_id)
    return settings["shuffle"]

async def copy_queue(guild_id, shuffle=False):
    """複製隊列內容而不消耗原隊列"""
    queue = guild_queues.get(guild_id)
    if not queue:
        return [], asyncio.Queue()
        
    queue_copy = []
    temp_queue = asyncio.Queue()
    
    # 複製隊列內容
    while not queue.empty():
        item = await queue.get()
        queue_copy.append(item)
    
    # 如果啟用隨機播放，打亂順序
    if shuffle:
        random.shuffle(queue_copy)
    
    # 重新填充隊列
    for item in queue_copy:
        await temp_queue.put(item)
    
    guild_queues[guild_id] = temp_queue
    return queue_copy, temp_queue
