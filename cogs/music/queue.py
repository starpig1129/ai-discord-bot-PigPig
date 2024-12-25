import os
import asyncio
import random
import logging as logger

# 定義每個伺服器的播放清單、設置和播放清單追蹤
guild_queues = {}
guild_settings = {}
guild_playlists = {}  # 用於追蹤播放清單的剩餘歌曲

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
    if guild_id in guild_playlists:
        guild_playlists[guild_id] = []

def set_guild_playlist(guild_id, video_infos):
    """設置伺服器的播放清單"""
    guild_playlists[guild_id] = video_infos

async def get_next_playlist_songs(guild_id, count=1, youtube_manager=None, folder=None, interaction=None):
    """獲取播放清單中的下一首歌曲"""
    if guild_id not in guild_playlists:
        return []
    
    songs = guild_playlists[guild_id][:count]
    guild_playlists[guild_id] = guild_playlists[guild_id][count:]
    
    # 如果提供了youtube_manager，下載歌曲
    if youtube_manager and folder and interaction:
        downloaded_songs = []
        for song in songs:
            if "file_path" not in song:  # 如果歌曲還沒有下載
                video_info, error = await youtube_manager.download_audio(song["url"], folder, interaction)
                if video_info:
                    downloaded_songs.append(video_info)
            else:
                downloaded_songs.append(song)
        return downloaded_songs
    
    return songs

def has_playlist_songs(guild_id):
    """檢查是否還有播放清單歌曲"""
    return guild_id in guild_playlists and len(guild_playlists[guild_id]) > 0

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
    original_queue = asyncio.Queue()
    
    # 複製隊列內容
    while not queue.empty():
        item = await queue.get()
        queue_copy.append(item)
    
    # 如果啟用隨機播放，打亂順序
    items_to_queue = queue_copy.copy()
    if shuffle:
        random.shuffle(items_to_queue)
    
    # 重新填充臨時隊列和原始隊列
    for item in items_to_queue:
        await temp_queue.put(item)
    for item in queue_copy:
        await original_queue.put(item)
    
    # 更新原始隊列
    guild_queues[guild_id] = original_queue
    
    return queue_copy, temp_queue
