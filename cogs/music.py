import os
import asyncio
import discord
from discord import FFmpegPCMAudio
from discord.ui import Button, View, Select
from discord.ext import commands
from pytubefix import YouTube
from discord import app_commands
import logging as logger
from youtube_search import YoutubeSearch
import random

# 定義每個伺服器的播放清單
guild_queues = {}

# 確保伺服器有獨立的資料夾和播放清單
def get_guild_queue_and_folder(guild_id):
    if guild_id not in guild_queues:
        guild_queues[guild_id] = asyncio.Queue()

    # 為每個伺服器設定獨立的下載資料夾
    guild_folder = f"./temp/music/{guild_id}"
    if not os.path.exists(guild_folder):
        os.makedirs(guild_folder)
    return guild_queues[guild_id], guild_folder

class ProgressBar(discord.ui.Modal, title='調整播放進度'):
    def __init__(self, view, duration):
        super().__init__()
        self.view = view
        self.duration = duration
        minutes, seconds = divmod(duration, 60)
        
        self.time = discord.ui.TextInput(
            label=f'輸入時間 (格式: 分:秒，最大 {minutes:02d}:{seconds:02d})',
            placeholder='例如: 1:30',
            required=True,
            max_length=5
        )
        self.add_item(self.time)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # 解析輸入的時間
            time_parts = self.time.value.split(':')
            if len(time_parts) != 2:
                raise ValueError("Invalid time format")
            
            minutes = int(time_parts[0])
            seconds = int(time_parts[1])
            total_seconds = minutes * 60 + seconds
            
            if total_seconds > self.duration:
                await interaction.response.send_message("❌ 輸入的時間超過歌曲長度！", ephemeral=True)
                return
                
            # 更新進度
            self.view.current_position = total_seconds
            voice_client = interaction.guild.voice_client
            if voice_client and voice_client.is_playing():
                # 這裡需要實現跳轉功能，但 Discord.py 不直接支持
                # 所以我們重新播放並快進到指定位置
                voice_client.stop()
                await self.view.cog.play_from_position(interaction, total_seconds)
                
            await interaction.response.send_message("✅ 已調整播放進度！", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ 時間格式錯誤，請使用 分:秒 格式！", ephemeral=True)

class MusicControlView(View):
    def __init__(self, interaction: discord.Interaction, cog):
        super().__init__(timeout=None)
        self.guild = interaction.guild
        self.cog = cog
        self.current_position = 0
        self.message = None
        self.update_task = None
        self.current_embed = None

    def create_progress_bar(self, current, total, length=20):
        filled = int(length * current / total)
        bar = "▰" * filled + "▱" * (length - filled)
        minutes_current, seconds_current = divmod(current, 60)
        minutes_total, seconds_total = divmod(total, 60)
        return f"{minutes_current:02d}:{seconds_current:02d} {bar} {minutes_total:02d}:{seconds_total:02d}"

    async def update_progress(self, duration):
        try:
            while True:
                if not self.guild.voice_client or not self.guild.voice_client.is_playing():
                    break
                
                self.current_position += 1
                if self.current_position > duration:
                    break
                    
                if self.current_embed and self.message:
                    progress_bar = self.create_progress_bar(self.current_position, duration)
                    self.current_embed.set_field_at(3, name="🎵 播放進度 (點擊調整)", value=progress_bar, inline=False)
                    await self.message.edit(embed=self.current_embed)
                
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Progress update error: {e}")

    async def update_embed(self, interaction: discord.Interaction, title: str, color: discord.Color = discord.Color.blue()):
        if self.current_embed and self.message:
            self.current_embed.title = title
            self.current_embed.color = color
            await self.message.edit(embed=self.current_embed)

    @discord.ui.button(emoji='⏮️', style=discord.ButtonStyle.gray)
    async def previous(self, interaction: discord.Interaction, button: Button):
        voice_client = self.guild.voice_client
        if voice_client:
            # 重置當前歌曲
            voice_client.stop()
            # 將當前歌曲重新加入隊列前端
            if hasattr(self.cog, 'current_song') and self.cog.current_song:
                queue = guild_queues.get(self.guild.id)
                if queue:
                    new_queue = asyncio.Queue()
                    await new_queue.put(self.cog.current_song)
                    while not queue.empty():
                        item = await queue.get()
                        await new_queue.put(item)
                    guild_queues[self.guild.id] = new_queue
            await self.update_embed(interaction, f"⏮️ {interaction.user.name} 返回上一首")
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='⏯️', style=discord.ButtonStyle.gray)
    async def toggle_playback(self, interaction: discord.Interaction, button: Button):
        voice_client = self.guild.voice_client
        if voice_client:
            if voice_client.is_playing():
                voice_client.pause()
                await self.update_embed(interaction, f"⏸️ {interaction.user.name} 暫停了音樂")
            elif voice_client.is_paused():
                voice_client.resume()
                await self.update_embed(interaction, f"▶️ {interaction.user.name} 繼續了音樂")
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.gray)
    async def skip(self, interaction: discord.Interaction, button: Button):
        voice_client = self.guild.voice_client
        if voice_client:
            voice_client.stop()
            await self.update_embed(interaction, f"⏭️ {interaction.user.name} 跳過了音樂")
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='⏹️', style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: Button):
        voice_client = self.guild.voice_client
        if voice_client:
            # 清空播放隊列
            queue = guild_queues.get(self.guild.id)
            if queue:
                while not queue.empty():
                    await queue.get()
            # 停止播放
            voice_client.stop()
            await voice_client.disconnect()
            await self.update_embed(interaction, f"⏹️ {interaction.user.name} 停止了播放", discord.Color.red())
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='📜', style=discord.ButtonStyle.gray)
    async def show_queue(self, interaction: discord.Interaction, button: Button):
        queue = guild_queues.get(self.guild.id)
        if not queue or queue.empty():
            await interaction.response.send_message("目前沒有歌曲在播放清單中", ephemeral=True)
            return

        # 複製隊列內容而不消耗原隊列
        queue_copy = []
        temp_queue = asyncio.Queue()
        while not queue.empty():
            item = await queue.get()
            queue_copy.append(item)
            await temp_queue.put(item)
        guild_queues[self.guild.id] = temp_queue

        # 更新播放清單到當前 embed
        if self.current_embed and self.message:
            queue_text = ""
            for i, item in enumerate(queue_copy, 1):
                minutes, seconds = divmod(item["duration"], 60)
                queue_text += f"{i}. {item['title']} | {minutes:02d}:{seconds:02d}\n"
            
            self.current_embed.set_field_at(4, name="📜 播放清單", value=queue_text if queue_text else "清單為空", inline=False)
            await self.message.edit(embed=self.current_embed)
            await interaction.response.defer()
        else:
            await interaction.response.send_message("無法更新播放清單", ephemeral=True)

    @discord.ui.button(label="調整進度", style=discord.ButtonStyle.gray)
    async def adjust_progress(self, interaction: discord.Interaction, button: Button):
        if not self.guild.voice_client or not hasattr(self.cog, 'current_song'):
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)
            return
            
        modal = ProgressBar(self, self.cog.current_song["duration"])
        await interaction.response.send_modal(modal)

class YTMusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.limit = 1800  # 時長<30min
        self.current_song = None  # 保存當前播放的歌曲信息
        
    async def play_from_position(self, interaction: discord.Interaction, position: int):
        """從指定位置開始播放當前歌曲"""
        if not self.current_song:
            return
            
        voice_client = interaction.guild.voice_client
        if not voice_client:
            return
            
        file_path = self.current_song["file_path"]
        if not os.path.exists(file_path):
            return
            
        # 重新開始播放
        voice_client.play(
            FFmpegPCMAudio(file_path),
            after=lambda e: self.bot.loop.create_task(self.handle_after_play(interaction, file_path))
        )
        
        # 更新進度條位置
        view = interaction.message.view
        if view:
            view.current_position = position

    @app_commands.command(name="play", description="播放影片(網址或關鍵字)")
    async def play(self, interaction: discord.Interaction, query: str = ""):
        
        # 檢查使用者是否已在語音頻道
        if interaction.user.voice:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:  # 檢查機器人是否已在語音頻道
                await channel.connect()
        else:
            embed = discord.Embed(title="❌ | 請先加入語音頻道！", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        # 如果有提供查詢，將音樂加入播放清單
        if query:
            logger.info(f"[音樂] 伺服器 ID： {interaction.guild.id}, 使用者名稱： {interaction.user.name}, 使用者輸入： {query}")
            # 檢查是否為URL
            if "youtube.com" in query or "youtu.be" in query:
                is_valid = await self.add_to_queue(interaction, query)
            else:
                # 使用關鍵字搜尋
                try:
                    results = YoutubeSearch(query, max_results=10).to_dict()
                    if not results:
                        embed = discord.Embed(title="❌ | 未找到相關影片", color=discord.Color.red())
                        await interaction.response.send_message(embed=embed)
                        return
                    
                    # 創建選擇菜單
                    view = SongSelectView(self, results, interaction)
                    
                    # 創建包含搜尋結果的embed
                    embed = discord.Embed(title="🔍 | YouTube搜尋結果", description="請選擇要播放的歌曲：", color=discord.Color.blue())
                    for i, result in enumerate(results, 1):
                        duration = result.get('duration', 'N/A')
                        embed.add_field(
                            name=f"{i}. {result['title']}", 
                            value=f"頻道: {result['channel']}\n時長: {duration}", 
                            inline=False
                        )
                    
                    await interaction.response.send_message(embed=embed, view=view)
                    return
                    
                except Exception as e:
                    logger.error(f"[音樂] 伺服器 ID： {interaction.guild.id}, 搜尋失敗： {e}")
                    embed = discord.Embed(title="❌ | 搜尋失敗", color=discord.Color.red())
                    await interaction.response.send_message(embed=embed)
                    return
            if is_valid == False:
                return
        
        # 播放音樂
        voice_client = interaction.guild.voice_client
        if not voice_client.is_playing():
            await self.play_next(interaction)

    async def add_to_queue(self, interaction, url):
        guild_id = interaction.guild.id
        queue, folder = get_guild_queue_and_folder(guild_id)

        try:
            # 使用 pytubefix 並指定 get_audio_only 方法
            yt = YouTube(url)
            audio_stream = yt.streams.get_audio_only()
            file_path = os.path.join(folder, f"{yt.video_id}.mp3")

            # 控制時長
            if yt.length > self.limit:
                logger.info(f"[音樂] 伺服器 ID： {interaction.guild.id}, 使用者名稱： {interaction.user.name}, 影片時間過長！")
                embed = discord.Embed(title=f"❌ | 影片時間過長！超過 {self.limit/60} 分鐘", color=discord.Color.red())
                await interaction.response.send_message(embed=embed)
                return False

            # 下載 mp3
            if not os.path.exists(file_path):  # 避免重複下載
                audio_stream.download(output_path=folder, filename=f"{yt.video_id}.mp3")
            
            # 將檔案路徑與標題作為字典加入佇列
            await queue.put({"file_path": file_path, "title": yt.title, "url": url, "duration": yt.length, "video_id": yt.video_id,
                             "author": yt.author, "views": yt.views, "requester": interaction.user, "user_avatar": interaction.user.avatar.url})

            logger.debug(f"[音樂] 伺服器 ID： {interaction.guild.id}, 使用者名稱： {interaction.user.name}, 成功將 {yt.title} 添加到播放清單")
            embed = discord.Embed(title=f"✅ | 已添加到播放清單： {yt.title}", color=discord.Color.blue())
            await interaction.response.send_message(embed=embed)
            return True
        except Exception as e:
            logger.error(f"[音樂] 伺服器 ID： {interaction.guild.id}, 使用者名稱： {interaction.user.name}, 下載失敗： {e}")
            embed = discord.Embed(title="❌ | 下載失敗", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)

    async def play_next(self, interaction):
        guild_id = interaction.guild.id
        queue, _ = get_guild_queue_and_folder(guild_id)
        view = MusicControlView(interaction, self)

        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return
        if not queue.empty():
            item = await queue.get()
            file_path = item["file_path"]
            try:
                # 保存當前播放的歌曲信息
                self.current_song = item
                
                # 創建控制視圖
                view = MusicControlView(interaction, self)
                
                # 開始播放
                voice_client.play(
                    FFmpegPCMAudio(file_path),
                    after=lambda e: self.bot.loop.create_task(self.handle_after_play(interaction, file_path))
                )
                # 音樂資訊
                title = item["title"]
                url = item["url"]
                author = item["author"]
                duration = item["duration"]
                video_id = item["video_id"]
                thumbnail = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                views = item["views"]
                minutes, seconds = divmod(duration, 60)
                requester = item["requester"]
                user_avatar = item["user_avatar"]
                
                # 創建更豐富的 embed
                embed = discord.Embed(
                    title="🎵 正在播放",
                    description=f"**[{title}]({url})**",
                    color=discord.Color.blue()
                )
                embed.add_field(name="👤 上傳頻道", value=author, inline=True)
                embed.add_field(name="⏱️ 播放時長", value=f"{minutes:02d}:{seconds:02d}", inline=True)
                embed.add_field(name="👀 觀看次數", value=f"{int(views):,}", inline=True)
                embed.add_field(name="🎵 播放進度 (點擊調整)", value=view.create_progress_bar(0, duration), inline=False)
                embed.add_field(name="📜 播放清單", value="清單為空", inline=False)
                embed.set_thumbnail(url=thumbnail)
                embed.set_footer(text=f"由 {requester.name} 添加", icon_url=user_avatar)
                
                # 發送 embed 和控制視圖
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message
                view.current_embed = embed
                view.current_position = 0
                
                # 開始更新進度
                if view.update_task:
                    view.update_task.cancel()
                view.update_task = self.bot.loop.create_task(view.update_progress(duration))
            except Exception as e:
                logger.error(f"[音樂] 伺服器 ID： {interaction.guild.id}, 播放音樂時出錯： {e}")
                embed = discord.Embed(title=f"❌ | 播放音樂時出錯", color=discord.Color.red())
                await interaction.followup.send(embed=embed)
                await self.play_next(interaction)  # 嘗試播放下一首
        else:
            embed = discord.Embed(title="🌟 | 播放清單已播放完畢！", color=discord.Color.blue())
            await interaction.followup.send(embed=embed)

    async def handle_after_play(self, interaction, file_path):
        try:
            if os.path.exists(file_path):
                await asyncio.sleep(1)
                os.remove(file_path)
                logger.debug(f"[音樂] 伺服器 ID： {interaction.guild.id}, 刪除檔案成功！")
        except Exception as e:
            logger.warning(f"[音樂] 伺服器 ID： {interaction.guild.id}, 刪除檔案失敗： {e}")
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


class SongSelectView(View):
    def __init__(self, cog, results, original_interaction):
        super().__init__(timeout=60)
        self.cog = cog
        self.results = results
        self.original_interaction = original_interaction
        
        # 創建選擇菜單
        options = []
        for i, result in enumerate(results, 1):
            options.append(discord.SelectOption(
                label=f"{i}. {result['title'][:80]}", # Discord限制選項標籤最多100字符
                description=f"{result['channel']} | {result.get('duration', 'N/A')}",
                value=str(i-1)
            ))
            
        select = Select(
            placeholder="選擇要播放的歌曲...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        # 獲取選擇的歌曲
        selected_index = int(interaction.data['values'][0])
        selected_result = self.results[selected_index]
        video_url = f"https://www.youtube.com{selected_result['url_suffix']}"
        
        # 添加到播放佇列
        is_valid = await self.cog.add_to_queue(interaction, video_url)
        if is_valid:
            # 如果佇列是空的且沒有正在播放，開始播放
            voice_client = interaction.guild.voice_client
            if voice_client and not voice_client.is_playing():
                await self.cog.play_next(self.original_interaction)
        
        # 禁用選擇菜單
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

async def setup(bot):
    await bot.add_cog(YTMusic(bot))
