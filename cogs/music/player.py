import os
import asyncio
import random
import discord
from discord import FFmpegPCMAudio
from discord.ext import commands
from discord import app_commands
import logging as logger

from .queue import (
    get_guild_queue_and_folder,
    guild_queues,
    PlayMode,
    get_play_mode,
    set_play_mode,
    is_shuffle_enabled,
    toggle_shuffle,
    copy_queue,
    set_guild_playlist,
    get_next_playlist_songs,
    has_playlist_songs
)
from .youtube import YouTubeManager
from .ui.controls import MusicControlView
from .ui.song_select import SongSelectView
from .ui.progress import ProgressDisplay
class YTMusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.youtube = YouTubeManager()
        self.current_song = None
        self.current_message = None
        
    async def update_player_ui(self, interaction, item, view=None):
        """更新播放器UI"""
        if not self.current_message:
            return
            
        embed = discord.Embed(
            title="🎵 正在播放",
            description=f"**[{item['title']}]({item['url']})**",
            color=discord.Color.blue()
        )
        
        minutes, seconds = divmod(item['duration'], 60)
        embed.add_field(name="👤 上傳頻道", value=item['author'], inline=True)
        embed.add_field(name="⏱️ 播放時長", value=f"{minutes:02d}:{seconds:02d}", inline=True)
        embed.add_field(name="👀 觀看次數", value=f"{int(item['views']):,}", inline=True)
        progress_bar = ProgressDisplay.create_progress_bar(0, item['duration'])
        embed.add_field(name="🎵 播放進度", value=progress_bar, inline=False)
        embed.add_field(name="📜 播放清單", value="清單為空", inline=False)
        
        thumbnail = self.youtube.get_thumbnail_url(item['video_id'])
        embed.set_thumbnail(url=thumbnail)
        embed.set_footer(text=f"由 {item['requester'].name} 添加", icon_url=item['user_avatar'])
        
        if not view:
            view = MusicControlView(interaction, self)
            
        await self.current_message.edit(embed=embed, view=view)
        
        # 設置視圖的訊息和 embed
        view.message = self.current_message
        view.current_embed = embed
        view.current_position = 0
        
        # 取消舊的更新任務
        if hasattr(self, '_current_view') and self._current_view and self._current_view.update_task:
            self._current_view.update_task.cancel()
            await asyncio.sleep(0.1)  # 等待任務完全取消
            
        # 保存新的視圖引用
        self._current_view = view
        
        # 開始更新進度
        view.update_task = self.bot.loop.create_task(view.update_progress(item['duration']))

    @app_commands.command(name="mode", description="設置播放模式 (不循環/清單循環/單曲循環)")
    async def mode(self, interaction: discord.Interaction, mode: str):
        """播放模式命令"""
        if mode not in ["no_loop", "loop_queue", "loop_single"]:
            embed = discord.Embed(
                title="❌ | 無效的播放模式", 
                description="可用模式: no_loop (不循環), loop_queue (清單循環), loop_single (單曲循環)", 
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
            
        set_play_mode(interaction.guild.id, mode)
        mode_names = {
            "no_loop": "不循環",
            "loop_queue": "清單循環",
            "loop_single": "單曲循環"
        }
        embed = discord.Embed(title=f"✅ | 已設置播放模式為: {mode_names[mode]}", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="shuffle", description="切換隨機播放")
    async def shuffle(self, interaction: discord.Interaction):
        """隨機播放命令"""
        is_shuffle = toggle_shuffle(interaction.guild.id)
        status = "開啟" if is_shuffle else "關閉"
        embed = discord.Embed(title=f"✅ | 已{status}隨機播放", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="play", description="播放影片(網址或關鍵字)")
    async def play(self, interaction: discord.Interaction, query: str = ""):
        """播放音樂命令"""
        # 檢查使用者是否已在語音頻道
        if interaction.user.voice:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:
                await channel.connect()
        else:
            embed = discord.Embed(title="❌ | 請先加入語音頻道！", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        # 如果有提供查詢，將音樂加入播放清單
        if query:
            logger.info(f"[音樂] 伺服器 ID： {interaction.guild.id}, 使用者名稱： {interaction.user.name}, 使用者輸入： {query}")
            
            await interaction.response.defer()
            
            # 檢查是否為URL
            if "youtube.com" in query or "youtu.be" in query:
                # 檢查是否為播放清單
                if "playlist" in query:
                    queue, folder = get_guild_queue_and_folder(interaction.guild.id)
                    video_infos, error = await self.youtube.download_playlist(query, folder, interaction)
                    if error:
                        embed = discord.Embed(title=f"❌ | {error}", color=discord.Color.red())
                        await interaction.followup.send(embed=embed)
                        return
                    
                    # 檢查隊列中的歌曲數量
                    queue_size = 0
                    queue_copy = []
                    while not queue.empty():
                        item = await queue.get()
                        queue_copy.append(item)
                        queue_size += 1
                    
                    # 重新將歌曲放回隊列
                    for item in queue_copy:
                        await queue.put(item)
                    
                    # 計算需要添加的歌曲數量
                    songs_to_add = min(5 - queue_size, len(video_infos))
                    
                    # 將歌曲加入隊列
                    added_songs = video_infos[:songs_to_add]
                    for video_info in added_songs:
                        await queue.put(video_info)
                    
                    # 保存剩餘歌曲到播放清單，並確保它們按順序添加
                    remaining_songs = video_infos[songs_to_add:]
                    if remaining_songs:
                        set_guild_playlist(interaction.guild.id, remaining_songs)
                        logger.debug(f"[音樂] 伺服器 ID： {interaction.guild.id}, 已保存 {len(remaining_songs)} 首歌曲到播放清單")
                        
                        # 如果隊列為空或未滿，立即添加更多歌曲
                        remaining_space = 5 - queue_size
                        if remaining_space > 0:
                            next_songs = await get_next_playlist_songs(
                                interaction.guild.id,
                                count=remaining_space,
                                youtube_manager=self.youtube,
                                folder=folder,
                                interaction=interaction
                            )
                            if next_songs:
                                for song in next_songs:
                                    await queue.put(song)
                                logger.debug(f"[音樂] 伺服器 ID： {interaction.guild.id}, 已立即添加 {len(next_songs)} 首播放清單歌曲")
                    
                    # 創建嵌入訊息顯示已加入的歌曲
                    description = "\n".join([f"🎵 {info['title']}" for info in added_songs])
                    embed = discord.Embed(
                        title=f"✅ | 已添加 {len(added_songs)} 首歌曲到播放清單 (共 {len(video_infos)} 首)",
                        description=description,
                        color=discord.Color.blue()
                    )
                    await interaction.followup.send(embed=embed)
                    is_valid = True
                else:
                    is_valid = await self.add_to_queue(interaction, query, is_deferred=True)
            else:
                # 使用關鍵字搜尋
                results = await self.youtube.search_videos(query)
                if not results:
                    embed = discord.Embed(title="❌ | 未找到相關影片", color=discord.Color.red())
                    await interaction.followup.send(embed=embed)
                    return
                
                # 創建選擇菜單
                view = SongSelectView(self, results, interaction)
                
                # 創建簡潔的搜尋結果embed
                description = "請選擇要播放的歌曲：\n\n" + "\n".join([
                    f"{i}. {result['title']} ({result.get('duration', 'N/A')})"
                    for i, result in enumerate(results, 1)
                ])
                embed = discord.Embed(
                    title="🔍 | YouTube搜尋結果",
                    description=description,
                    color=discord.Color.blue()
                )
                
                await interaction.followup.send(embed=embed, view=view)
                return
                
            if is_valid == False:
                return
        
        # 播放音樂
        voice_client = interaction.guild.voice_client
        if not voice_client.is_playing():
            await self.play_next(interaction)

    async def add_to_queue(self, interaction, url, is_deferred=False):
        guild_id = interaction.guild.id
        queue, folder = get_guild_queue_and_folder(guild_id)

        # 檢查隊列中的歌曲數量
        queue_size = 0
        queue_copy = []
        while not queue.empty():
            item = await queue.get()
            queue_copy.append(item)
            queue_size += 1
        
        # 重新將歌曲放回隊列
        for item in queue_copy:
            await queue.put(item)

        # 如果隊列已滿，則不添加新歌曲
        if queue_size >= 5:
            embed = discord.Embed(
                title="❌ | 播放清單已滿",
                description="請等待當前歌曲播放完畢後再添加新歌曲",
                color=discord.Color.red()
            )
            if is_deferred:
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)
            return False

        # 下載並獲取影片資訊
        video_info, error = await self.youtube.download_audio(url, folder, interaction)
        
        if error:
            embed = discord.Embed(title=f"❌ | {error}", color=discord.Color.red())
            if is_deferred:
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)
            return False

        # 將檔案資訊加入佇列
        await queue.put(video_info)

        logger.debug(f"[音樂] 伺服器 ID： {interaction.guild.id}, 使用者名稱： {interaction.user.name}, 成功將 {video_info['title']} 添加到播放清單")
        embed = discord.Embed(title=f"✅ | 已添加到播放清單： {video_info['title']}", color=discord.Color.blue())
        if is_deferred:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)
        return True

    async def play_next(self, interaction, force_new=False):
        guild_id = interaction.guild.id
        queue, _ = get_guild_queue_and_folder(guild_id)

        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return
            
        play_mode = get_play_mode(guild_id)
        
        # 處理播放模式
        if not force_new and play_mode == PlayMode.LOOP_SINGLE and self.current_song:
            # 單曲循環：重新創建音頻源
            item = self.current_song
            file_path = item["file_path"]
            if not os.path.exists(file_path):
                await self.play_next(interaction, force_new=True)
                return
            
            try:
                # 確保語音客戶端準備就緒
                if voice_client.is_playing():
                    voice_client.stop()
                    await asyncio.sleep(0.2)  # 短暫延遲等待停止完成
                
                # 等待確保完全停止
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)
                
                await asyncio.sleep(0.3)  # 額外延遲確保穩定
                
                # 取消舊的更新任務
                if hasattr(self, '_current_view') and self._current_view and self._current_view.update_task:
                    self._current_view.update_task.cancel()
                    await asyncio.sleep(0.1)  # 等待任務完全取消
                
                # 創建新的控制視圖並重置進度
                view = MusicControlView(interaction, self)
                self._current_view = view
                
                if self.current_message:
                    await self.update_player_ui(interaction, item, view)
                
                # 直接重新播放當前歌曲
                voice_client.play(
                    FFmpegPCMAudio(file_path),
                    after=lambda e: asyncio.run_coroutine_threadsafe(
                        self.handle_after_play(interaction, file_path),
                        self.bot.loop
                    )
                )
                return
            except Exception as e:
                logger.error(f"[音樂] 伺服器 ID： {interaction.guild.id}, 單曲循環播放時出錯： {e}")
                await self.play_next(interaction, force_new=True)
                return
        elif not queue.empty() or (play_mode == PlayMode.LOOP_QUEUE and self.current_song):
            # 如果隊列為空但是循環模式，重新添加所有歌曲
            if queue.empty() and play_mode == PlayMode.LOOP_QUEUE:
                queue_copy, _ = await copy_queue(guild_id)
                if queue_copy:
                    # 如果啟用隨機播放，打亂順序
                    if is_shuffle_enabled(guild_id):
                        random.shuffle(queue_copy)
                    for song in queue_copy:
                        await queue.put(song)
            # 獲取下一首歌曲
            if not play_mode == PlayMode.LOOP_SINGLE or force_new:
                # 如果啟用隨機播放，重新排序整個隊列
                if is_shuffle_enabled(guild_id):
                    queue_copy, new_queue = await copy_queue(guild_id, shuffle=True)
                    guild_queues[guild_id] = new_queue
                
                item = await queue.get()
                file_path = item["file_path"]
                self.current_song = item
            try:
                # 保存當前播放的歌曲信息
                self.current_song = item
                
                # 確保語音客戶端準備就緒
                if voice_client.is_playing():
                    voice_client.stop()
                    await asyncio.sleep(0.2)  # 短暫延遲等待停止完成
                
                # 等待確保完全停止
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)
                
                await asyncio.sleep(0.3)  # 額外延遲確保穩定
                
                # 開始播放
                voice_client.play(
                    FFmpegPCMAudio(file_path),
                    after=lambda e: asyncio.run_coroutine_threadsafe(
                        self.handle_after_play(interaction, file_path),
                        self.bot.loop
                    )
                )
                
                # 創建新的控制視圖
                view = MusicControlView(interaction, self)
                
                # 如果已有播放訊息，則更新它
                if self.current_message:
                    await self.update_player_ui(interaction, item, view)
                else:
                    # 創建初始embed
                    embed = discord.Embed(
                        title="🎵 正在播放",
                        description=f"**[{item['title']}]({item['url']})**",
                        color=discord.Color.blue()
                    )
                    minutes, seconds = divmod(item['duration'], 60)
                    embed.add_field(name="👤 上傳頻道", value=item['author'], inline=True)
                    embed.add_field(name="⏱️ 播放時長", value=f"{minutes:02d}:{seconds:02d}", inline=True)
                    embed.add_field(name="👀 觀看次數", value=f"{int(item['views']):,}", inline=True)
                    progress_bar = ProgressDisplay.create_progress_bar(0, item['duration'])
                    embed.add_field(name="🎵 播放進度", value=progress_bar, inline=False)
                    embed.add_field(name="📜 播放清單", value="清單為空", inline=False)
                    thumbnail = self.youtube.get_thumbnail_url(item['video_id'])
                    embed.set_thumbnail(url=thumbnail)
                    embed.set_footer(text=f"由 {item['requester'].name} 添加", icon_url=item['user_avatar'])
                    
                    # 發送新訊息
                    message = await interaction.followup.send(embed=embed, view=view)
                    self.current_message = message
                    
                    # 設置視圖的訊息和 embed
                    view.message = message
                    view.current_embed = embed
                    view.current_position = 0
                    
                    # 開始更新進度
                    if view.update_task:
                        view.update_task.cancel()
                    view.update_task = self.bot.loop.create_task(view.update_progress(item['duration']))
                
            except Exception as e:
                logger.error(f"[音樂] 伺服器 ID： {interaction.guild.id}, 播放音樂時出錯： {e}")
                embed = discord.Embed(title=f"❌ | 播放音樂時出錯", color=discord.Color.red())
                await interaction.followup.send(embed=embed)
                await self.play_next(interaction, force_new=True)  # 嘗試播放下一首
        else:
            # 播放清單已空
            embed = discord.Embed(title="🌟 | 播放清單已播放完畢！", color=discord.Color.blue())
            await interaction.followup.send(embed=embed)
            self.current_message = None

    async def handle_after_play(self, interaction, file_path):
        guild_id = interaction.guild.id
        queue = guild_queues.get(guild_id)

        # 只在非單曲循環模式下刪除檔案
        play_mode = get_play_mode(guild_id)
        if play_mode != PlayMode.LOOP_SINGLE:
            try:
                if os.path.exists(file_path):
                    await asyncio.sleep(1)
                    os.remove(file_path)
                    logger.debug(f"[音樂] 伺服器 ID： {interaction.guild.id}, 刪除檔案成功！")
            except Exception as e:
                logger.warning(f"[音樂] 伺服器 ID： {interaction.guild.id}, 刪除檔案失敗： {e}")

        # 檢查隊列中的歌曲數量
        queue_size = 0
        queue_copy = []
        if queue:
            while not queue.empty():
                item = await queue.get()
                queue_copy.append(item)
                queue_size += 1

            # 重新將歌曲放回隊列
            for item in queue_copy:
                await queue.put(item)

            # 如果隊列未滿且有更多播放清單歌曲，添加到隊列
            if queue_size < 5 and has_playlist_songs(guild_id):
                remaining_space = 5 - queue_size
                _, folder = get_guild_queue_and_folder(guild_id)
                next_songs = await get_next_playlist_songs(
                    guild_id,
                    count=remaining_space,
                    youtube_manager=self.youtube,
                    folder=folder,
                    interaction=interaction
                )
                if next_songs:
                    for song in next_songs:
                        await queue.put(song)
                        queue_size += 1
                    logger.debug(f"[音樂] 伺服器 ID： {guild_id}, 已添加 {len(next_songs)} 首播放清單歌曲")

        # 如果隊列為空且有播放清單歌曲，直接添加下一首
        elif has_playlist_songs(guild_id):
            _, folder = get_guild_queue_and_folder(guild_id)
            next_songs = await get_next_playlist_songs(
                guild_id,
                count=1,
                youtube_manager=self.youtube,
                folder=folder,
                interaction=interaction
            )
            if next_songs:
                await queue.put(next_songs[0])
                queue_size = 1
                logger.debug(f"[音樂] 伺服器 ID： {guild_id}, 已添加下一首播放清單歌曲")

        # 檢查播放模式並處理下一首歌曲
        play_mode = get_play_mode(guild_id)
        if play_mode == PlayMode.LOOP_SINGLE and self.current_song:
            # 在單曲循環模式下，直接重新播放當前歌曲
            voice_client = interaction.guild.voice_client
            if voice_client and voice_client.is_connected():
                try:
                    # 確保語音客戶端準備就緒
                    if voice_client.is_playing():
                        voice_client.stop()
                        await asyncio.sleep(0.2)  # 短暫延遲等待停止完成
                    
                    # 等待確保完全停止
                    while voice_client.is_playing():
                        await asyncio.sleep(0.1)
                    
                    await asyncio.sleep(0.3)  # 額外延遲確保穩定
                    
                    # 取消舊的更新任務
                    if hasattr(self, '_current_view') and self._current_view and self._current_view.update_task:
                        self._current_view.update_task.cancel()
                        await asyncio.sleep(0.1)  # 等待任務完全取消
                    
                    # 創建新的控制視圖並重置進度
                    view = MusicControlView(interaction, self)
                    self._current_view = view
                    
                    if self.current_message:
                        await self.update_player_ui(interaction, self.current_song, view)
                    
                    # 開始播放
                    voice_client.play(
                        FFmpegPCMAudio(file_path),
                        after=lambda e: asyncio.run_coroutine_threadsafe(
                            self.handle_after_play(interaction, file_path),
                            self.bot.loop
                        )
                    )
                    return
                except Exception as e:
                    logger.error(f"[音樂] 伺服器 ID： {interaction.guild.id}, 單曲循環重播時出錯： {e}")
                    logger.error(str(e))  # 記錄詳細錯誤信息
        
        # 非單曲循環模式或重播失敗時，播放下一首
        await self.play_next(interaction)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # 偵測機器人離開語音頻道時，清理伺服器相關資料
        if member.bot and before.channel is not None and after.channel is None:
            guild_id = member.guild.id
            _, folder = get_guild_queue_and_folder(guild_id)
            logger.info(f"[音樂] 伺服器 ID： {member.guild.id}, 離開語音頻道")
            await asyncio.sleep(2)
            # 刪除所有音檔
            for file in os.listdir(folder):
                file_path = os.path.join(folder, file)
                try:
                    os.remove(file_path)
                    logger.debug(f"[音樂] 伺服器 ID： {member.guild.id}, 刪除檔案成功！")
                except Exception as e:
                    logger.warning(f"[音樂] 伺服器 ID： {member.guild.id}, 刪除檔案失敗： {e}")
            
            # 清空播放隊列
            if guild_id in guild_queues:
                guild_queues[guild_id] = asyncio.Queue()
            
            # 清除當前訊息引用
            self.current_message = None
