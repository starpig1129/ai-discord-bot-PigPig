import asyncio
import os
import random
from typing import List, Dict, Any, Tuple, Optional
from enum import Enum
import logging as logger

class PlayMode(Enum):
    NO_LOOP = "no_loop"
    LOOP_QUEUE = "loop_queue"
    LOOP_SINGLE = "loop_single"

class QueueManager:
    MAX_QUEUE_SIZE = 50
    
    def __init__(self, bot=None):
        self.bot = bot
        self.guild_queues: Dict[int, asyncio.Queue] = {}
        self.guild_settings: Dict[int, Dict[str, Any]] = {}
        self.guild_playlists: Dict[int, List[Dict[str, Any]]] = {}

    def get_guild_settings(self, guild_id: int) -> Dict[str, Any]:
        """獲取伺服器的播放設置"""
        if guild_id not in self.guild_settings:
            self.guild_settings[guild_id] = {
                "play_mode": PlayMode.NO_LOOP.value,
                "shuffle": False
            }
        return self.guild_settings[guild_id]

    def get_guild_queue_and_folder(self, guild_id: int) -> Tuple[asyncio.Queue, str]:
        """確保伺服器有獨立的資料夾和播放清單"""
        if guild_id not in self.guild_queues:
            self.guild_queues[guild_id] = asyncio.Queue()

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        guild_folder = os.path.join(base_dir, "temp", "music", str(guild_id))
        os.makedirs(guild_folder, exist_ok=True)
        return self.guild_queues[guild_id], guild_folder

    def get_queue(self, guild_id: int) -> asyncio.Queue:
        """為 guild 取得佇列"""
        q, _ = self.get_guild_queue_and_folder(guild_id)
        return q

    def clear_guild_data(self, guild_id: int):
        """清空指定伺服器的播放清單"""
        if guild_id in self.guild_queues:
            self.guild_queues[guild_id] = asyncio.Queue()
        if guild_id in self.guild_settings:
            self.guild_settings[guild_id]["play_mode"] = PlayMode.NO_LOOP.value
            self.guild_settings[guild_id]["shuffle"] = False
        if guild_id in self.guild_playlists:
            self.guild_playlists[guild_id] = []

    def set_playlist(self, guild_id: int, video_infos: List[Dict[str, Any]]):
        """設置伺服器的播放清單"""
        self.guild_playlists[guild_id] = video_infos

    async def get_next_playlist_songs(self, guild_id: int, count: int = 1, youtube_manager=None, folder: Optional[str] = None, interaction=None) -> List[Dict[str, Any]]:
        """獲取播放清單中的下一首歌曲"""
        if guild_id not in self.guild_playlists:
            return []
        
        songs = self.guild_playlists[guild_id][:count]
        self.guild_playlists[guild_id] = self.guild_playlists[guild_id][count:]
        
        if youtube_manager and folder and interaction:
            downloaded_songs = []
            for song in songs:
                if "file_path" not in song:
                    video_info, error = await youtube_manager.download_audio(song["url"], folder, interaction)
                    if video_info:
                        downloaded_songs.append(video_info)
                else:
                    downloaded_songs.append(song)
            return downloaded_songs
        
        return songs

    def has_playlist_songs(self, guild_id: int) -> bool:
        """檢查是否還有播放清單歌曲"""
        return guild_id in self.guild_playlists and len(self.guild_playlists[guild_id]) > 0

    def toggle_shuffle(self, guild_id: int) -> bool:
        """切換隨機播放狀態"""
        settings = self.get_guild_settings(guild_id)
        settings["shuffle"] = not settings["shuffle"]
        return settings["shuffle"]

    def set_play_mode(self, guild_id: int, mode: PlayMode):
        """設置播放模式"""
        settings = self.get_guild_settings(guild_id)
        settings["play_mode"] = mode.value

    def get_play_mode(self, guild_id: int) -> PlayMode:
        """獲取播放模式"""
        settings = self.get_guild_settings(guild_id)
        return PlayMode(settings["play_mode"])

    def is_shuffle_enabled(self, guild_id: int) -> bool:
        """檢查是否啟用隨機播放"""
        settings = self.get_guild_settings(guild_id)
        return settings["shuffle"]

    async def copy_queue(self, guild_id: int, shuffle: bool = False) -> Tuple[List[Dict[str, Any]], asyncio.Queue]:
        """複製隊列內容而不消耗原隊列"""
        queue = self.guild_queues.get(guild_id)
        if not queue:
            return [], asyncio.Queue()
            
        queue_copy = []
        temp_queue = asyncio.Queue()
        original_queue = asyncio.Queue()
        
        while not queue.empty():
            item = await queue.get()
            queue_copy.append(item)
        
        items_to_queue = queue_copy.copy()
        if shuffle:
            random.shuffle(items_to_queue)
        
        for item in items_to_queue:
            await temp_queue.put(item)
        for item in queue_copy:
            await original_queue.put(item)
        
        self.guild_queues[guild_id] = original_queue
        
        return queue_copy, temp_queue

    def get_queue_snapshot(self, guild_id: int) -> List[Dict[str, Any]]:
        """獲取當前播放隊列的快照"""
        queue = self.guild_queues.get(guild_id)
        if not queue or queue.empty():
            return []
        return list(queue._queue).copy()

    def is_queue_empty(self, guild_id: int) -> bool:
        """檢查佇列是否為空"""
        q = self.guild_queues.get(guild_id)
        return not q or q.empty()

    def clear_queue(self, guild_id: int):
        """清空指定伺服器的播放隊列"""
        if guild_id in self.guild_queues:
            self.guild_queues[guild_id] = asyncio.Queue()

    def set_queue(self, guild_id: int, q: asyncio.Queue):
        """為特定 guild 設置佇列"""
        self.guild_queues[guild_id] = q

    async def add_to_queue(self, guild_id: int, item: Dict[str, Any], force: bool = False):
        """
        將項目添加到佇列，並根據添加者（使用者或自動播放）應用不同的邏輯。
        """
        q = self.get_queue(guild_id)
        queue_list = list(q._queue)

        # 除非強制，否則檢查歌曲是否已存在於佇列中
        if not force:
            video_id = item.get('video_id')
            if any(song.get('video_id') == video_id for song in queue_list):
                logger.info(f"歌曲 '{item.get('title')}' 已存在於佇列中，跳過新增。")
                return

        added_by_user = 'added_by' in item and item['added_by'] != self.bot.user.id

        if added_by_user:
            # 使用者新增歌曲
            if len(queue_list) >= self.MAX_QUEUE_SIZE:
                # 佇列已滿，嘗試從末尾移除一首自動播放的歌曲
                autoplay_song_removed = False
                for i in range(len(queue_list) - 1, -1, -1):
                    if queue_list[i].get('added_by') == self.bot.user.id:
                        del queue_list[i]
                        autoplay_song_removed = True
                        break
                
                if not autoplay_song_removed:
                    logger.warning(f"佇列已滿，且沒有自動播放歌曲可移除 (guild_id: {guild_id})。")
                    return

            # 找到第一首自動播放歌曲的索引
            insert_index = -1
            for i, song in enumerate(queue_list):
                if song.get('added_by') == self.bot.user.id:
                    insert_index = i
                    break
            
            if insert_index != -1:
                # 將歌曲插入到第一首自動播放歌曲之前
                queue_list.insert(insert_index, item)
            else:
                # 如果沒有自動播放歌曲，則添加到末尾
                queue_list.append(item)
        else:
            # 自動播放新增歌曲
            if len(queue_list) >= self.MAX_QUEUE_SIZE:
                logger.warning(f"佇列已滿 (guild_id: {guild_id})，自動播放無法新增歌曲。")
                return
            queue_list.append(item)

        # 重建佇列
        new_queue = asyncio.Queue()
        for song in queue_list:
            await new_queue.put(song)
        self.guild_queues[guild_id] = new_queue

    async def add_to_front_of_queue(self, guild_id: int, item: Dict[str, Any]) -> bool:
        """將項目添加到佇列的前面，並處理佇列溢出。成功返回 True，失敗返回 False。"""
        q = self.get_queue(guild_id)
        queue_list = list(q._queue)

        video_id = item.get('video_id')
        if any(song.get('video_id') == video_id for song in queue_list):
            logger.info(f"歌曲 '{item.get('title')}' 已存在於佇列中，跳過新增。")
            return True

        if len(queue_list) >= self.MAX_QUEUE_SIZE:
            # 佇列已滿，嘗試從末尾移除一首自動播放的歌曲
            autoplay_song_removed = False
            for i in range(len(queue_list) - 1, -1, -1):
                if queue_list[i].get('added_by') == self.bot.user.id:
                    del queue_list[i]
                    autoplay_song_removed = True
                    break
            
            if not autoplay_song_removed:
                logger.warning(f"佇列已滿，且沒有自動播放歌曲可移除 (guild_id: {guild_id})。")
                return False

        # 將歌曲新增到佇列前面
        queue_list.insert(0, item)

        # 重建佇列
        new_queue = asyncio.Queue()
        for song in queue_list:
            await new_queue.put(song)
        self.guild_queues[guild_id] = new_queue
        return True

    async def get_next_item(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """從佇列中獲取下一個項目"""
        q = self.get_queue(guild_id)
        if q.empty():
            return None
        return await q.get()

    async def enforce_autoplay_limit(self, guild_id: int, limit: int = 5):
        """確保佇列中由自動播放新增的歌曲不超過指定數量"""
        q = self.get_queue(guild_id)
        queue_list = list(q._queue)
        
        autoplay_songs_indices = [i for i, song in enumerate(queue_list) if song.get('added_by') == self.bot.user.id]
        
        if len(autoplay_songs_indices) > limit:
            # 計算需要移除的歌曲數量
            to_remove_count = len(autoplay_songs_indices) - limit
            
            # 獲取需要移除的歌曲的索引（從頭開始）
            indices_to_remove = set(autoplay_songs_indices[:to_remove_count])
            
            # 過濾掉需要移除的歌曲
            new_queue_list = [song for i, song in enumerate(queue_list) if i not in indices_to_remove]

            # 重建佇列
            new_queue = asyncio.Queue()
            for song in new_queue_list:
                await new_queue.put(song)
            self.guild_queues[guild_id] = new_queue
            logger.info(f"已從佇列 (guild_id: {guild_id}) 移除 {to_remove_count} 首多餘的自動播放歌曲。")
