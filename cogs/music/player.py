import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import logging as logger
from concurrent.futures import ThreadPoolExecutor

from .youtube import YouTubeManager
from .audio_manager import AudioManager
from .state_manager import StateManager
from .queue_manager import QueueManager, PlayMode
from .ui_manager import UIManager
from .ui.song_select import SongSelectView

class YTMusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.youtube = None  # Will be initialized in setup_hook
        self._executor = ThreadPoolExecutor(max_workers=3)
        
        # Initialize managers
        self.audio_manager = AudioManager()
        self.state_manager = StateManager()
        self.queue_manager = QueueManager()
        self.ui_manager = UIManager()

    async def setup_hook(self):
        """Initialize async components"""
        self.youtube = await YouTubeManager.create()

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
            
        self.queue_manager.set_play_mode(interaction.guild.id, mode)
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
        is_shuffle = self.queue_manager.toggle_shuffle(interaction.guild.id)
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
            logger.info(f"[音樂] 伺服器 ID： {interaction.guild.name}, 使用者名稱： {interaction.user.name}, 使用者輸入： {query}")
            await interaction.response.defer()
            
            # 檢查是否為URL
            if "youtube.com" in query or "youtu.be" in query:
                # 檢查是否為播放清單
                if "list" in query:
                    await self._handle_playlist(interaction, query)
                else:
                    is_valid = await self._handle_single_video(interaction, query)
                    if not is_valid:
                        return
            else:
                await self._handle_search(interaction, query)
                return
        
        # 播放音樂
        voice_client = interaction.guild.voice_client
        if not voice_client.is_playing():
            await self.play_next(interaction)

    async def _handle_playlist(self, interaction: discord.Interaction, url: str):
        """Handle playlist URL"""
        _, folder = self._get_guild_folder(interaction.guild.id)
        video_infos, error = await self.youtube.download_playlist(url, folder, interaction)
        
        if error:
            embed = discord.Embed(title=f"❌ | {error}", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return
            
        # Add initial songs to queue
        queue_size = self.queue_manager.get_queue(interaction.guild.id).qsize()
        songs_to_add = min(5 - queue_size, len(video_infos))
        added_songs = video_infos[:songs_to_add]
        
        for video_info in added_songs:
            await self.queue_manager.add_to_queue(interaction.guild.id, video_info)
            
        # Save remaining songs to playlist
        remaining_songs = video_infos[songs_to_add:]
        if remaining_songs:
            self.queue_manager.set_playlist(interaction.guild.id, remaining_songs)
            
        # Create embed for added songs
        description = "\n".join([f"🎵 {info['title']}" for info in added_songs])
        embed = discord.Embed(
            title=f"✅ | 已添加 {len(added_songs)} 首歌曲到播放清單 (共 {len(video_infos)} 首)",
            description=description,
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)

    async def _handle_single_video(self, interaction: discord.Interaction, url: str) -> bool:
        """Handle single video URL"""
        guild_id = interaction.guild.id
        queue = self.queue_manager.get_queue(guild_id)
        
        if queue.qsize() >= 5:
            embed = discord.Embed(
                title="❌ | 播放清單已滿",
                description="請等待當前歌曲播放完畢後再添加新歌曲",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return False
            
        _, folder = self._get_guild_folder(guild_id)
        should_download = queue.qsize() == 0
        
        if should_download:
            video_info, error = await self.youtube.download_audio(url, folder, interaction)
        else:
            video_info, error = await self.youtube.get_video_info_without_download(url, interaction)
            
        if error:
            embed = discord.Embed(title=f"❌ | {error}", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return False
            
        await self.queue_manager.add_to_queue(guild_id, video_info)
        embed = discord.Embed(title=f"✅ | 已添加到播放清單： {video_info['title']}", color=discord.Color.blue())
        await interaction.followup.send(embed=embed)
        return True

    async def _handle_search(self, interaction: discord.Interaction, query: str):
        """Handle search query"""
        results = await self.youtube.search_videos(query)
        if not results:
            embed = discord.Embed(title="❌ | 未找到相關影片", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return
            
        view = SongSelectView(self, results, interaction)
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

    async def play_next(self, interaction: discord.Interaction, force_new: bool = False):
        """Play the next song in queue"""
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not voice_client.is_connected():
            return
            
        state = self.state_manager.get_state(guild_id)
        play_mode = self.queue_manager.get_play_mode(guild_id)
        
        try:
            # Handle single song loop
            if not force_new and play_mode == PlayMode.LOOP_SINGLE and state.current_song:
                await self._handle_single_loop(interaction, state, voice_client)
                return
                
            # Get next song from queue
            next_song = await self._get_next_song(interaction, guild_id, force_new)
            if not next_song:
                embed = discord.Embed(title="🌟 | 播放清單已播放完畢！", color=discord.Color.blue())
                await interaction.followup.send(embed=embed)
                self.state_manager.update_state(guild_id, current_message=None)
                return
                
            # Update state and play song
            self.state_manager.update_state(guild_id, current_song=next_song)
            await self._play_song(interaction, next_song, voice_client)
            
        except Exception as e:
            logger.error(f"[音樂] 伺服器 ID： {guild_id}, 播放音樂時出錯： {e}")
            embed = discord.Embed(title=f"❌ | 播放音樂時出錯", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            await self.play_next(interaction, force_new=True)

    async def _handle_single_loop(self, interaction: discord.Interaction, state, voice_client):
        """Handle single song loop playback"""
        try:
            if voice_client.is_playing():
                voice_client.stop()
            
            file_path = state.current_song["file_path"]
            audio_source = self.audio_manager.create_audio_source(file_path)
            
            message = await self.ui_manager.update_player_ui(
                interaction, 
                state.current_song,
                state.current_message,
                self.youtube,
                self
            )
            self.state_manager.update_state(interaction.guild.id, current_message=message)
            
            def after_callback(error):
                if error:
                    logger.error(f"[音樂] 播放時發生錯誤: {error}")
                
                # Get the event loop from the bot
                loop = self.bot.loop
                if loop and loop.is_running():
                    # Schedule the coroutine on the bot's event loop
                    loop.create_task(self._handle_after_play(interaction, file_path))
                
            voice_client.play(audio_source, after=after_callback)
        except Exception as e:
            logger.error(f"[音樂] 單曲循環播放時出錯： {e}")
            await self.play_next(interaction, force_new=True)

    async def _get_next_song(self, interaction: discord.Interaction, guild_id: int, force_new: bool):
        """Get the next song to play"""
        if force_new or self.queue_manager.get_play_mode(guild_id) != PlayMode.LOOP_SINGLE:
            # Handle queue loop
            if self.queue_manager.get_queue(guild_id).empty():
                if self.queue_manager.get_play_mode(guild_id) == PlayMode.LOOP_QUEUE:
                    await self._refill_queue(guild_id)
                    
            # Get and download next song
            next_song = await self.queue_manager.get_next_item(guild_id)
            if next_song:
                _, folder = self._get_guild_folder(guild_id)
                if not next_song.get('file_path'):
                    downloaded_info, error = await self.youtube.download_audio(
                        next_song['url'], 
                        folder, 
                        interaction
                    )
                    if error:
                        return None
                    next_song['file_path'] = downloaded_info['file_path']
            return next_song
        return None

    async def _refill_queue(self, guild_id: int):
        """Refill the queue with songs"""
        queue_copy, new_queue = await self.queue_manager.copy_queue(
            guild_id, 
            shuffle=self.queue_manager.is_shuffle_enabled(guild_id)
        )
        if queue_copy:
            self.queue_manager.get_queue_state(guild_id).queue = new_queue

    async def _play_song(self, interaction: discord.Interaction, song: dict, voice_client):
        """Play a song and update UI"""
        if voice_client.is_playing():
            voice_client.stop()
            
        audio_source = self.audio_manager.create_audio_source(song['file_path'])
        message = await self.ui_manager.update_player_ui(
            interaction,
            song,
            self.state_manager.get_state(interaction.guild.id).current_message,
            self.youtube,
            self
        )
        self.state_manager.update_state(interaction.guild.id, current_message=message)
        
        def after_callback(error):
            if error:
                logger.error(f"[音樂] 播放時發生錯誤: {error}")
            
            # Get the event loop from the bot
            loop = self.bot.loop
            if loop and loop.is_running():
                # Schedule the coroutine on the bot's event loop
                loop.create_task(self._handle_after_play(interaction, song['file_path']))
            
        voice_client.play(audio_source, after=after_callback)

    async def _handle_after_play(self, interaction: discord.Interaction, file_path: str):
        """Handle cleanup after song finishes playing"""
        guild_id = interaction.guild.id
        channel = interaction.channel
        
        try:
            # Clean up file if not in single loop mode
            if self.queue_manager.get_play_mode(guild_id) != PlayMode.LOOP_SINGLE:
                await self.audio_manager.delete_file(guild_id, file_path)
            
            # Add more songs from playlist if needed
            queue = self.queue_manager.get_queue(guild_id)
            if queue.qsize() < 5 and self.queue_manager.has_playlist_songs(guild_id):
                _, folder = self._get_guild_folder(guild_id)
                next_songs = await self.queue_manager.get_next_playlist_songs(
                    guild_id,
                    count=5 - queue.qsize()
                )
                for song in next_songs:
                    await self.queue_manager.add_to_queue(guild_id, song)
            
            # Create a new interaction-like object for UI updates
            if channel:
                class DummyInteraction:
                    def __init__(self, channel, guild, original_interaction):
                        self.channel = channel
                        self.guild = guild
                        # Create a complete user copy with all required attributes
                        class DummyUser:
                            def __init__(self, original_user):
                                self.name = original_user.name
                                self.display_name = original_user.display_name
                                self.id = original_user.id
                                self.mention = original_user.mention
                                self.display_avatar = original_user.display_avatar
                                self.avatar = type('Avatar', (), {'url': original_user.display_avatar.url})()
                            
                            def __getattr__(self, name):
                                # Forward any other attribute access to the original user
                                return getattr(original_interaction.user, name)
                                
                        self.user = DummyUser(original_interaction.user)
                        # Create a followup object with proper send method
                        class DummyFollowup:
                            def __init__(self, channel):
                                self._channel = channel
                            
                            async def send(self, *args, **kwargs):
                                try:
                                    return await self._channel.send(*args, **kwargs)
                                except Exception as e:
                                    logger.error(f"[音樂] 發送訊息失敗： {str(e)}")
                                    raise
                                    
                        self.followup = DummyFollowup(channel)
                        # Copy additional required attributes
                        self.application_id = original_interaction.application_id
                        self.id = original_interaction.id
                        
                new_interaction = DummyInteraction(channel, interaction.guild, interaction)
                
                # Play next song with new interaction object
                try:
                    # Try to play next song
                    await self.play_next(new_interaction)
                except Exception as e:
                    logger.error(f"[音樂] 播放下一首歌曲時出錯： {str(e)}")
                    if channel:
                        try:
                            # Send error message using channel.send directly
                            embed = discord.Embed(
                                title="❌ | 播放音樂時發生錯誤",
                                description="正在嘗試播放下一首歌曲...",
                                color=discord.Color.red()
                            )
                            await channel.send(embed=embed)
                            
                            # Try to stop current playback if any
                            voice_client = interaction.guild.voice_client
                            if voice_client and voice_client.is_connected() and voice_client.is_playing():
                                voice_client.stop()
                            
                            # Try one more time with force_new
                            await self.play_next(new_interaction, force_new=True)
                        except Exception as retry_error:
                            logger.error(f"[音樂] 重試播放失敗： {str(retry_error)}")
                            try:
                                # Send final error message
                                embed = discord.Embed(
                                    title="❌ | 播放失敗",
                                    description="請使用 /play 重新播放",
                                    color=discord.Color.red()
                                )
                                await channel.send(embed=embed)
                            except Exception as final_error:
                                logger.error(f"[音樂] 發送錯誤訊息失敗： {str(final_error)}")
            
        except Exception as e:
            logger.error(f"[音樂] 處理播放完成時出錯： {str(e)}")

    def _get_guild_folder(self, guild_id: int) -> tuple:
        """Get guild queue and folder"""
        queue = self.queue_manager.get_queue(guild_id)
        folder = f"./temp/music/{guild_id}"
        return queue, folder

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle bot leaving voice channel"""
        if member.bot and before.channel is not None and after.channel is None:
            guild_id = member.guild.id
            _, folder = self._get_guild_folder(guild_id)
            
            # Cleanup
            await self.audio_manager.cleanup_guild_files(guild_id, folder)
            self.queue_manager.clear_guild_data(guild_id)
            self.state_manager.clear_state(guild_id)
            
            if logger.getLogger().isEnabledFor(logger.INFO):
                logger.info(f"[音樂] 伺服器 ID： {member.guild.name}, 離開語音頻道")
