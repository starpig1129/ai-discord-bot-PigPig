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
    copy_queue
)
from .youtube import YouTubeManager
from .ui.controls import MusicControlView
from .ui.song_select import SongSelectView

class YTMusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.youtube = YouTubeManager()
        self.current_song = None
        self.current_message = None

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
        try:
            for component in interaction.message.components:
                for child in component.children:
                    if isinstance(child, discord.ui.Select):
                        child.placeholder = f"目前位置: {position//60:02d}:{position%60:02d}"
            await interaction.message.edit(view=interaction.message.view)
        except Exception as e:
            logger.error(f"更新進度條位置失敗: {e}")

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
                    
                    # 將所有歌曲加入隊列
                    for video_info in video_infos:
                        await queue.put(video_info)
                    
                    embed = discord.Embed(
                        title=f"✅ | 已添加播放清單: {len(video_infos)} 首歌曲",
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
                
                # 創建包含搜尋結果的embed
                embed = discord.Embed(title="🔍 | YouTube搜尋結果", description="請選擇要播放的歌曲：", color=discord.Color.blue())
                for i, result in enumerate(results, 1):
                    duration = result.get('duration', 'N/A')
                    embed.add_field(
                        name=f"{i}. {result['title']}", 
                        value=f"頻道: {result['channel']}\n時長: {duration}", 
                        inline=False
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
        
        # 處理單曲循環
        if play_mode == PlayMode.LOOP_SINGLE and not force_new and self.current_song:
            item = self.current_song
            file_path = item["file_path"]
        # 處理其他模式
        elif not queue.empty():
            # 如果啟用隨機播放，重新排序隊列
            if is_shuffle_enabled(guild_id):
                queue_copy, new_queue = await copy_queue(guild_id, shuffle=True)
                guild_queues[guild_id] = new_queue
            
            item = await queue.get()
            file_path = item["file_path"]
            try:
                # 保存當前播放的歌曲信息
                self.current_song = item
                
                # 開始播放
                voice_client.play(
                    FFmpegPCMAudio(file_path),
                    after=lambda e: self.bot.loop.create_task(self.handle_after_play(interaction, file_path))
                )
                
                # 創建或更新 embed
                embed = discord.Embed(
                    title="🎵 正在播放",
                    description=f"**[{item['title']}]({item['url']})**",
                    color=discord.Color.blue()
                )
                
                minutes, seconds = divmod(item['duration'], 60)
                embed.add_field(name="👤 上傳頻道", value=item['author'], inline=True)
                embed.add_field(name="⏱️ 播放時長", value=f"{minutes:02d}:{seconds:02d}", inline=True)
                embed.add_field(name="👀 觀看次數", value=f"{int(item['views']):,}", inline=True)
                embed.add_field(name="🎵 播放進度", value=f"00:00 ▱▱▱▱▱▱▱▱▱▱ {minutes:02d}:{seconds:02d}", inline=False)
                embed.add_field(name="📜 播放清單", value="清單為空", inline=False)
                
                thumbnail = self.youtube.get_thumbnail_url(item['video_id'])
                embed.set_thumbnail(url=thumbnail)
                embed.set_footer(text=f"由 {item['requester'].name} 添加", icon_url=item['user_avatar'])
                
                # 創建新的控制視圖並添加進度條選擇器
                view = MusicControlView(interaction, self)
                view.add_progress_select()
                
                # 如果已有播放訊息，則更新它
                if self.current_message:
                    await self.current_message.edit(embed=embed, view=view)
                    message = self.current_message
                else:
                    # 否則發送新訊息
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
            # 處理清單循環
            if play_mode == PlayMode.LOOP_QUEUE and self.current_song:
                # 重新加入所有歌曲到隊列
                queue_copy, _ = await copy_queue(guild_id)
                if queue_copy:
                    # 如果啟用隨機播放，打亂順序
                    if is_shuffle_enabled(guild_id):
                        random.shuffle(queue_copy)
                    for song in queue_copy:
                        await queue.put(song)
                    await self.play_next(interaction)
                    return
            
            embed = discord.Embed(title="🌟 | 播放清單已播放完畢！", color=discord.Color.blue())
            await interaction.followup.send(embed=embed)
            self.current_message = None

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
            
            # 清除當前訊息引用
            self.current_message = None
