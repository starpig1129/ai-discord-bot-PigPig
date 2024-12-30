import discord
import asyncio
import logging as logger
from .progress import ProgressDisplay
from ..queue import (
    guild_queues,
    PlayMode,
    get_play_mode,
    set_play_mode,
    is_shuffle_enabled,
    toggle_shuffle,
    get_guild_queue_and_folder,
    has_playlist_songs,
    get_next_playlist_songs
)

class MusicControlView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, cog):
        super().__init__(timeout=None)
        self.guild = interaction.guild
        self.cog = cog
        self.current_position = 0
        self.message = None
        self.update_task = None
        self.current_embed = None

    async def update_progress(self, duration):
        try:
            # 確保只有一個更新任務在運行
            if hasattr(self, '_is_updating') and self._is_updating:
                return
                
            self._is_updating = True
            update_interval = 1
            last_update = 0
            
            try:
                while True:
                    if not self.guild.voice_client or not self.guild.voice_client.is_playing():
                        break
                        
                    self.current_position += 1
                    if self.current_position > duration:
                        break
                        
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_update >= update_interval:
                        if self.current_embed and self.message:
                            # 使用新的進度條顯示
                            progress_bar = ProgressDisplay.create_progress_bar(self.current_position, duration)
                            self.current_embed.set_field_at(3, name="🎵 播放進度", value=progress_bar, inline=False)
                            
                            # 更新訊息
                            try:
                                await self.message.edit(embed=self.current_embed, view=self)
                                last_update = current_time
                            except discord.errors.HTTPException as e:
                                logger.error(f"更新進度條位置失敗: {e}")
                    
                    await asyncio.sleep(1)
            finally:
                self._is_updating = False
                # 確保任務被正確取消時清理狀態
                if hasattr(self, 'update_task'):
                    self.update_task = None
        except Exception as e:
            logger.error(f"Progress update error: {e}")

    async def update_embed(self, interaction: discord.Interaction, title: str, color: discord.Color = discord.Color.blue()):
        if self.current_embed and self.message:
            self.current_embed.title = title
            self.current_embed.color = color
            await self.message.edit(embed=self.current_embed)

    @discord.ui.button(emoji='⏮️', style=discord.ButtonStyle.gray)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)
            return

        # 獲取當前播放的歌曲和隊列
        current_song = self.cog.current_song
        queue = guild_queues.get(self.guild.id)
        if not queue:
            await interaction.response.send_message("❌ 沒有可播放的歌曲！", ephemeral=True)
            return

        # 複製隊列內容
        queue_items = []
        temp_queue = asyncio.Queue()
        while not queue.empty():
            item = await queue.get()
            queue_items.append(item)

        # 重新組織隊列順序
        new_queue = asyncio.Queue()
        if current_song:
            await new_queue.put(current_song)  # 將當前歌曲放到最前面
        for item in queue_items:
            await new_queue.put(item)

        # 取消並清理更新任務
        if self.update_task:
            self.update_task.cancel()
            self.update_task = None
            self._is_updating = False
            
        # 更新隊列並停止當前播放
        guild_queues[self.guild.id] = new_queue
        voice_client.stop()
        
        # 更新UI
        await self.update_embed(interaction, f"⏮️ {interaction.user.name} 返回上一首")
        
        # 清理視圖引用，讓新的視圖可以正確初始化
        if hasattr(self.cog, '_current_view'):
            self.cog._current_view = None
        await interaction.response.defer()

    @discord.ui.button(emoji='⏯️', style=discord.ButtonStyle.gray)
    async def toggle_playback(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if voice_client:
            if voice_client.is_playing():
                voice_client.pause()
                await self.update_embed(interaction, f"⏸️ {interaction.user.name} 暫停了音樂")
                # 取消並清理更新任務
                if self.update_task:
                    self.update_task.cancel()
                    self.update_task = None
                    self._is_updating = False
            elif voice_client.is_paused():
                voice_client.resume()
                await self.update_embed(interaction, f"▶️ {interaction.user.name} 繼續了音樂")
                # 確保沒有運行中的任務
                if self.update_task:
                    self.update_task.cancel()
                    self.update_task = None
                    self._is_updating = False
                # 重新啟動進度更新
                if hasattr(self.cog, 'current_song'):
                    self.update_task = self.cog.bot.loop.create_task(
                        self.update_progress(self.cog.current_song["duration"])
                    )
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.gray)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)
            return

        # 檢查是否有下一首歌曲
        queue = guild_queues.get(self.guild.id)
        if not queue or queue.empty():
            # 檢查是否有播放清單中的歌曲可以添加
            if has_playlist_songs(self.guild.id):
                _, folder = get_guild_queue_and_folder(self.guild.id)
                next_songs = await get_next_playlist_songs(
                    self.guild.id,
                    count=1,
                    youtube_manager=self.cog.youtube,
                    folder=folder,
                    interaction=interaction
                )
                if next_songs:
                    await queue.put(next_songs[0])
                    logger.debug(f"[音樂] 伺服器 ID： {self.guild.id}, 已添加下一首播放清單歌曲")

        # 取消並清理更新任務
        if self.update_task:
            self.update_task.cancel()
            self.update_task = None
            self._is_updating = False
            
        # 停止當前播放，觸發播放下一首
        voice_client.stop()
        await self.update_embed(interaction, f"⏭️ {interaction.user.name} 跳過了音樂")
        
        # 清理視圖引用，讓新的視圖可以正確初始化
        if hasattr(self.cog, '_current_view'):
            self.cog._current_view = None
        await interaction.response.defer()

    @discord.ui.button(emoji='⏹️', style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if voice_client:
            # 清空播放隊列
            queue = guild_queues.get(self.guild.id)
            if queue:
                while not queue.empty():
                    await queue.get()
            # 取消並清理更新任務
            if self.update_task:
                self.update_task.cancel()
                self.update_task = None
                self._is_updating = False
            
            # 停止播放
            voice_client.stop()
            await voice_client.disconnect()
            await self.update_embed(interaction, f"⏹️ {interaction.user.name} 停止了播放", discord.Color.red())
            
            # 清理視圖引用
            if hasattr(self.cog, '_current_view'):
                self.cog._current_view = None
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='🔄', style=discord.ButtonStyle.gray)
    async def toggle_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換播放模式"""
        guild_id = self.guild.id
        current_mode = get_play_mode(guild_id)
        
        # 循環切換模式
        mode_order = [PlayMode.NO_LOOP, PlayMode.LOOP_QUEUE, PlayMode.LOOP_SINGLE]
        current_index = mode_order.index(current_mode)
        next_mode = mode_order[(current_index + 1) % len(mode_order)]
        
        set_play_mode(guild_id, next_mode)
        
        # 更新按鈕樣式
        mode_emojis = {
            PlayMode.NO_LOOP: '➡️',
            PlayMode.LOOP_QUEUE: '🔁',
            PlayMode.LOOP_SINGLE: '🔂'
        }
        button.emoji = mode_emojis[next_mode]
        
        mode_names = {
            PlayMode.NO_LOOP: "不循環",
            PlayMode.LOOP_QUEUE: "清單循環",
            PlayMode.LOOP_SINGLE: "單曲循環"
        }
        
        await self.update_embed(interaction, f"🔄 {interaction.user.name} 將播放模式設為 {mode_names[next_mode]}")
        await interaction.response.defer()

    @discord.ui.button(emoji='🔀', style=discord.ButtonStyle.gray)
    async def toggle_shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換隨機播放"""
        guild_id = self.guild.id
        is_shuffle = toggle_shuffle(guild_id)
        
        # 更新按鈕樣式
        button.style = discord.ButtonStyle.green if is_shuffle else discord.ButtonStyle.gray
        
        status = "開啟" if is_shuffle else "關閉"
        await self.update_embed(interaction, f"🔀 {interaction.user.name} {status}隨機播放")
        await interaction.response.defer()

    @discord.ui.button(emoji='📜', style=discord.ButtonStyle.gray)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = guild_queues.get(self.guild.id)
        
        # 獲取當前播放的歌曲和隊列中的歌曲
        current_song = self.cog.current_song
        queue_items = []
        
        if queue:
            # 複製隊列內容而不消耗原隊列
            temp_queue = asyncio.Queue()
            while not queue.empty():
                item = await queue.get()
                queue_items.append(item)
                await temp_queue.put(item)
            guild_queues[self.guild.id] = temp_queue

        # 更新播放清單到當前 embed
        if self.current_embed and self.message:
            queue_text = ""
            
            # 添加當前播放的歌曲
            if current_song:
                minutes, seconds = divmod(float(current_song["duration"]), 60)
                queue_text += f"▶️ 正在播放: {current_song['title']} | {int(minutes):02d}:{int(seconds):02d}\n\n"
            
            # 添加隊列中的歌曲
            if queue_items:
                queue_text += "待播放歌曲:\n"
                for i, item in enumerate(queue_items, 1):
                    minutes, seconds = divmod(float(item["duration"]), 60)
                    queue_text += f"{i}. {item['title']} | {int(minutes):02d}:{int(seconds):02d}\n"
            
            if not queue_text:
                queue_text = "清單為空"
            
            self.current_embed.set_field_at(4, name="📜 播放清單", value=queue_text, inline=False)
            await self.message.edit(embed=self.current_embed)
            await interaction.response.defer()
        else:
            await interaction.response.send_message("無法更新播放清單", ephemeral=True)
