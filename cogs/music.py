import asyncio
import os
import discord
from discord.ext import commands
from discord import app_commands
from addons.logging import get_logger
log = get_logger(source=__name__, server_id="system")
logger = log
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from addons.settings import music_config
from .music_lib.youtube import YouTubeManager
from .music_lib.audio_manager import AudioManager
from .music_lib.state_manager import StateManager
from .music_lib.queue_manager import QueueManager, PlayMode
from .music_lib.ui_manager import UIManager
from .music_lib.ui.song_select import SongSelectView
from cogs.language_manager import LanguageManager # Import LanguageManager
from function import func

class YTMusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.youtube = None  # Will be initialized in setup_hook
        self._executor = ThreadPoolExecutor(max_workers=3)
        self.settings = music_config
        
        # Initialize managers
        self.audio_manager = AudioManager()
        self.state_manager = bot.state_manager
        self.queue_manager = QueueManager(bot=bot)
        self.ui_manager = bot.ui_manager
        self.lang_manager: Optional[LanguageManager] = None # Initialize lang_manager
        self.disconnect_timers = {}

    async def setup_hook(self):
        """Initialize async components and LanguageManager"""
        self.youtube = await YouTubeManager.create()
        # Ensure LanguageManager is loaded after bot setup
        await asyncio.sleep(1) # Small delay to ensure bot is ready
        self.lang_manager = self.bot.get_cog("LanguageManager")
        if not self.lang_manager:
            logger.error("LanguageManager cog not found!")

    @app_commands.command(name="mode", description="設置播放模式 (不循環/清單循環/單曲循環)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="不循環", value="no_loop"),
        app_commands.Choice(name="清單循環", value="loop_queue"),
        app_commands.Choice(name="單曲循環", value="loop_single")
    ])
    async def mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        """播放模式命令"""
        guild_id = interaction.guild.id
        if not self.lang_manager: # Ensure lang_manager is loaded
             self.lang_manager = self.bot.get_cog("LanguageManager")
             if not self.lang_manager:
                 await interaction.response.send_message("Language manager not loaded.", ephemeral=True)
                 return
 
         # Localize choices (name is already localized by decorator, but value needs translation for response)
        mode_value = mode.value
        mode_name = self.lang_manager.translate(str(guild_id), "commands", "mode", "choices", mode_value)

        self.queue_manager.set_play_mode(guild_id, PlayMode(mode_value))

        title = self.lang_manager.translate(str(guild_id), "commands", "mode", "responses", "success", mode=mode_name)
        embed = discord.Embed(title=f"✅ | {title}", color=discord.Color.blue())
        message = await interaction.response.send_message(embed=embed)
        state = self.state_manager.get_state(interaction.guild.id)
        state.ui_messages.append(message)

    @app_commands.command(name="shuffle", description="切換隨機播放")
    async def shuffle(self, interaction: discord.Interaction):
        """隨機播放命令"""
        guild_id = interaction.guild.id
        if not self.lang_manager: # Ensure lang_manager is loaded
             self.lang_manager = self.bot.get_cog("LanguageManager")
             if not self.lang_manager:
                 await interaction.response.send_message("Language manager not loaded.", ephemeral=True)
                 return
 
        is_shuffle = self.queue_manager.toggle_shuffle(guild_id)
        status_key = "enabled" if is_shuffle else "disabled"
        status = self.lang_manager.translate(str(guild_id), "commands", "shuffle", "responses", status_key)
        title = self.lang_manager.translate(str(guild_id), "commands", "shuffle", "responses", "success", status=status)
        embed = discord.Embed(title=f"✅ | {title}", color=discord.Color.blue())
        message = await interaction.response.send_message(embed=embed)
        state = self.state_manager.get_state(interaction.guild.id)
        state.ui_messages.append(message)


    @app_commands.command(name="play", description="播放影片(網址或關鍵字) 或 刷新UI")
    async def play(self, interaction: discord.Interaction, query: Optional[str] = None):
        """播放音樂或刷新UI命令"""
        guild_id = interaction.guild.id
        
        # 檢查使用者是否已在語音頻道
        if not interaction.user.voice:
            if not self.lang_manager:
                self.lang_manager = self.bot.get_cog("LanguageManager")
            title = self.lang_manager.translate(str(guild_id), "commands", "play", "errors", "no_voice_channel")
            embed = discord.Embed(title=f"❌ | {title}", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        # 連接至語音頻道
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client is None:
            await channel.connect()

        # 如果沒有提供查詢，刷新UI
        if not query:
            state = self.state_manager.get_state(guild_id)
            voice_client = interaction.guild.voice_client
            
            is_active = not self.queue_manager.get_queue(guild_id).empty() or (voice_client and voice_client.is_playing())

            if is_active:
                await self.ui_manager.update_player_ui(
                    interaction,
                    state.current_song,
                    state.current_message,
                    self.youtube,
                    self
                )
                refresh_message = self.lang_manager.translate(str(guild_id), "commands", "play", "responses", "refreshed_ui")
                await interaction.response.send_message(refresh_message, ephemeral=True, delete_after=5)
            else:
                no_song_message = self.lang_manager.translate(str(guild_id), "commands", "play", "errors", "nothing_playing")
                await interaction.response.send_message(no_song_message, ephemeral=True, delete_after=5)
            return

        # 如果有提供查詢，將音樂加入播放清單
        logger.info(f"[音樂] 伺服器 ID： {interaction.guild.name}, 使用者名稱： {interaction.user.name}, 使用者輸入： {query}")
        
        # 檢查是否為URL
        if "youtube.com" in query or "youtu.be" in query:
            await interaction.response.defer(ephemeral=True)
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
        guild_id = interaction.guild.id
        _, folder = self._get_guild_folder(guild_id)
        video_infos, error = await self.youtube.download_playlist(url, folder, interaction)
        
        if error:
            title = self.lang_manager.translate(str(guild_id), "commands", "play", "errors", "playlist_download_failed", error=error)
            embed = discord.Embed(title=f"❌ | {title}", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
            
        # Add initial songs to queue
        queue_size = self.queue_manager.get_queue(interaction.guild.id).qsize()
        songs_to_add = min(5 - queue_size, len(video_infos))
        added_songs = video_infos[:songs_to_add]
        
        for video_info in added_songs:
            video_info['added_by'] = interaction.user.id
            await self.queue_manager.add_to_queue(interaction.guild.id, video_info)
            
        # Save remaining songs to playlist
        remaining_songs = video_infos[songs_to_add:]
        if remaining_songs:
            self.queue_manager.set_playlist(interaction.guild.id, remaining_songs)
            
        # Create embed for added songs
        description = "\n".join([f"🎵 {info['title']}" for info in added_songs])
        title = self.lang_manager.translate(str(guild_id), "commands", "play", "responses", "playlist_added", count=len(added_songs), total=len(video_infos))
        embed = discord.Embed(
            title=f"✅ | {title}",
            description=description,
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _handle_single_video(self, interaction: discord.Interaction, url: str) -> bool:
        """Handle single video URL"""
        guild_id = interaction.guild.id
        guild_id_str = str(guild_id)
        queue = self.queue_manager.get_queue(guild_id)
        
        _, folder = self._get_guild_folder(guild_id)
        should_download = queue.qsize() == 0
        
        if should_download:
            video_info, error = await self.youtube.download_audio(url, folder, interaction)
        else:
            video_info, error = await self.youtube.get_video_info_without_download(url, interaction)
            
        if error:
            title = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "video_info_failed", error=error)
            embed = discord.Embed(title=f"❌ | {title}", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return False
            
        video_info['added_by'] = interaction.user.id
        
        # 將歌曲加入佇列並檢查結果
        success = await self.queue_manager.add_to_front_of_queue(guild_id, video_info)
        
        if success:
            title = self.lang_manager.translate(guild_id_str, "commands", "play", "responses", "song_added", title=video_info['title'])
            embed = discord.Embed(title=f"✅ | {title}", color=discord.Color.blue())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return True
        else:
            title = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "queue_full_title")
            desc = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "queue_full_desc")
            embed = discord.Embed(
                title=f"❌ | {title}",
                description=desc,
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return False

    async def _handle_search(self, interaction: discord.Interaction, query: str):
        """Handle search query"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = await self.youtube.search_videos(query)
        guild_id = interaction.guild.id
        if not results:
            title = self.lang_manager.translate(str(guild_id), "commands", "play", "errors", "no_results")
            embed = discord.Embed(title=f"❌ | {title}", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Format durations properly
        formatted_results = []
        for i, result in enumerate(results, 1):
            duration_secs = result.get('duration', 0)
            minutes, seconds = divmod(duration_secs, 60)
            duration_str = f"{int(minutes):02d}:{int(seconds):02d}"
            formatted_results.append(f"{i}. {result['title']} ({duration_str})")

        view = SongSelectView(self, results, interaction)
        desc_prefix = self.lang_manager.translate(str(guild_id), "commands", "play", "responses", "select_song")
        description = f"{desc_prefix}\n\n" + "\n".join(formatted_results)
        embed_title = self.lang_manager.translate(str(guild_id), "commands", "play", "responses", "search_results_title")
        embed = discord.Embed(
            title=f"🔍 | {embed_title}",
            description=description,
            color=discord.Color.blue()
        )
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def play_next(self, interaction: discord.Interaction, force_new: bool = False):
        """Play the next song in queue"""
        guild_id = interaction.guild.id
        guild_id_str = str(guild_id)
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
                title = self.lang_manager.translate(guild_id_str, "commands", "play", "responses", "queue_finished")
                embed = discord.Embed(title=f"🌟 | {title}", color=discord.Color.blue())
                # Use followup if interaction is available, otherwise use channel.send
                if hasattr(interaction, 'followup') and not interaction.response.is_done():
                     message = await interaction.followup.send(embed=embed)
                elif interaction.channel:
                     message = await interaction.channel.send(embed=embed)
                else: # Fallback if channel is not available either
                     logger.warning("Cannot send queue finished message: no interaction followup or channel.")
                     message = None

                if message:
                    state = self.state_manager.get_state(guild_id)
                    state.ui_messages.append(message)
                self.state_manager.update_state(guild_id, current_song=None, current_message=None)
                return
                
            # Update state and play song
            self.state_manager.update_state(guild_id, current_song=next_song)
            await self._play_song(interaction, next_song, voice_client)
            
        except Exception as e:
            await func.report_error(e, f"playing next song in guild {guild_id}")
            title = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "playback_error")
            embed = discord.Embed(title=f"❌ | {title}", color=discord.Color.red())
            if hasattr(interaction, 'followup') and not interaction.response.is_done():
                 message = await interaction.followup.send(embed=embed)
            elif interaction.channel:
                 message = await interaction.channel.send(embed=embed)
            else:
                 message = None

            if message:
                state = self.state_manager.get_state(guild_id)
                state.ui_messages.append(message)
            await self.play_next(interaction, force_new=True)

    async def _handle_single_loop(self, interaction: discord.Interaction, state, voice_client):
        """Handle single song loop playback"""
        try:
            if voice_client.is_playing():
                voice_client.stop()
            
            song = state.current_song
            audio_source = self.audio_manager.create_audio_source(song)
            
            message = await self.ui_manager.update_player_ui(
                interaction, 
                state.current_song,
                state.current_message,
                self.youtube,
                music_cog=self
            )
            self.state_manager.update_state(interaction.guild.id, current_message=message)
            
            voice_client.play(audio_source)
            # For single loop, the loop is handled by play_next, not the player loop
            if not song.get('is_live') and self.queue_manager.get_play_mode(interaction.guild.id) != PlayMode.LOOP_SINGLE:
                self.bot.loop.create_task(self._player_loop(interaction, song))
        except Exception as e:
            await func.report_error(e, "handling single loop")
            await self.play_next(interaction, force_new=True)

    async def _get_next_song(self, interaction: discord.Interaction, guild_id: int, force_new: bool):
        """Get the next song to play, handling autoplay and ensuring download."""
        guild_id_str = str(guild_id)
        state = self.state_manager.get_state(guild_id)

        # --- Autoplay Logic: Fill queue if empty ---
        if state.autoplay and self.queue_manager.is_queue_empty(guild_id):
            await self._trigger_autoplay(interaction, guild_id)

        # --- Queue Logic: Get next song ---
        next_song = await self.queue_manager.get_next_item(guild_id)

        # --- Loop Logic ---
        if not next_song and self.queue_manager.get_play_mode(guild_id) == PlayMode.LOOP_QUEUE:
            await self._refill_queue(guild_id)
            next_song = await self.queue_manager.get_next_item(guild_id)

        if not next_song:
            return None

        # --- Download Logic: Ensure song is downloaded before playing ---
        if not next_song.get('is_live') and not next_song.get('file_path'):
            # 額外檢查檔案是否存在，以防狀態不一致
            _, folder = self._get_guild_folder(guild_id)
            potential_path = os.path.join(folder, f"{next_song.get('video_id')}.mp3")
            if not await asyncio.to_thread(os.path.exists, potential_path):
                logger.info(f"歌曲 '{next_song['title']}' 未下載，開始下載...")
                downloaded_info, error = await self.youtube.download_audio(next_song['url'], folder, interaction)
                if error:
                    logger.error(f"下載失敗: {next_song['title']} - {error}")
                    # Skip to the next song if download fails
                    return await self._get_next_song(interaction, guild_id, force_new)
                next_song.update(downloaded_info)
            else:
                logger.info(f"歌曲 '{next_song['title']}' 已存在於本地，更新檔案路徑。")
                next_song['file_path'] = potential_path

        return next_song

    async def _refill_queue(self, guild_id: int):
        """Refill the queue with songs"""
        queue_copy, new_queue = await self.queue_manager.copy_queue(
            guild_id, 
            shuffle=self.queue_manager.is_shuffle_enabled(guild_id)
        )
        if queue_copy:
            self.queue_manager.set_queue(guild_id, new_queue)

    async def _play_song(self, interaction: discord.Interaction, song: dict, voice_client):
        """Play a song and update UI"""
        await self._cancel_disconnect_timer(interaction.guild.id)
        if voice_client.is_playing():
            voice_client.stop()
            
        audio_source = self.audio_manager.create_audio_source(song)
        message = await self.ui_manager.update_player_ui(
            interaction,
            song,
            self.state_manager.get_state(interaction.guild.id).current_message,
            self.youtube,
            music_cog=self
        )
        self.state_manager.update_state(interaction.guild.id, current_message=message, current_song=song, last_played_song=song)
        
        voice_client.play(audio_source)
        if not song.get('is_live'):
            self.bot.loop.create_task(self._player_loop(interaction, song))

    async def _handle_after_play(self, interaction: discord.Interaction, song: dict):
        """Handle cleanup after song finishes playing"""
        guild_id = interaction.guild.id
        guild_id_str = str(guild_id)
        channel = interaction.channel
        
        try:
            state = self.state_manager.get_state(guild_id)
            current_song = state.current_song
            play_mode = self.queue_manager.get_play_mode(guild_id)
    
            # 如果是清單循環模式，將剛播放完的歌曲（包含檔案路徑）重新加入佇列
            if play_mode == PlayMode.LOOP_QUEUE and current_song:
                await self.queue_manager.add_to_queue(guild_id, current_song, force=True)
                logger.info(f"[音樂] 在清單循環模式下，將 '{current_song['title']}' 重新加入佇列。")
    
            # 只有在非循環且非直播的模式下才刪除檔案
            if play_mode not in [PlayMode.LOOP_SINGLE, PlayMode.LOOP_QUEUE] and not song.get('is_live'):
                file_path = song.get('file_path')
                if file_path:
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
                
                # Enforce autoplay limit after adding new songs
                await self.queue_manager.enforce_autoplay_limit(guild_id)

            # Trigger autoplay if enabled and not enough songs in queue
            if state.autoplay:
                queue_snapshot = self.queue_manager.get_queue_snapshot(guild_id)
                autoplay_song_count = sum(1 for s in queue_snapshot if s.get('added_by') == self.bot.user.id)
                if autoplay_song_count < 5:
                    await self._trigger_autoplay(interaction, guild_id)

            # Create a new interaction-like object for UI updates
            if channel:
                new_interaction = await self._create_dummy_interaction(channel, interaction.guild, interaction)
                
                # Play next song with new interaction object
                try:
                    # Try to play next song
                    await self.play_next(new_interaction)
                except Exception as e:
                    await func.report_error(e, "playing next song in _handle_after_play")
                    if channel:
                        try:
                            # Send error message using channel.send directly
                            title = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "playback_error")
                            desc = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "attempting_next")
                            embed = discord.Embed(
                                title=f"❌ | {title}",
                                description=desc,
                                color=discord.Color.red()
                            )
                            message = await channel.send(embed=embed)
                            state = self.state_manager.get_state(guild_id)
                            state.ui_messages.append(message)
                            
                            # Try to stop current playback if any
                            voice_client = interaction.guild.voice_client
                            if voice_client and voice_client.is_connected() and voice_client.is_playing():
                                voice_client.stop()
                            
                            # Try one more time with force_new
                            await self.play_next(new_interaction, force_new=True)
                        except Exception as retry_error:
                            await func.report_error(retry_error, "retrying to play next song in _handle_after_play")
                            try:
                                # Send final error message
                                title = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "playback_failed_title")
                                desc = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "playback_failed_desc")
                                embed = discord.Embed(
                                    title=f"❌ | {title}",
                                    description=desc,
                                    color=discord.Color.red()
                                )
                                message = await channel.send(embed=embed)
                                state = self.state_manager.get_state(guild_id)
                                state.ui_messages.append(message)
                            except Exception as final_error:
                                 await func.report_error(final_error, "sending final error message in _handle_after_play")
            
        except Exception as e:
             await func.report_error(e, "handling after play")

    async def _trigger_autoplay(self, interaction: discord.Interaction, guild_id: int):
        """根據最後播放的歌曲觸發自動播放，精確填充推薦歌曲至5首，並排除重複。"""
        state = self.state_manager.get_state(guild_id)
        
        queue_snapshot = self.queue_manager.get_queue_snapshot(guild_id)
        autoplay_song_count = sum(1 for s in queue_snapshot if s.get('added_by') == self.bot.user.id)
        
        needed = 5 - autoplay_song_count
        if needed <= 0:
            return

        logger.info(f"[音樂] Autoplay 已啟用，需要填充 {needed} 首推薦歌曲。")

        song_to_recommend_from = state.current_song or state.last_played_song
        if not song_to_recommend_from:
            logger.info("[音樂] 沒有可供推薦的歌曲。")
            return

        video_id = song_to_recommend_from.get("video_id")
        title = song_to_recommend_from.get("title")
        author = song_to_recommend_from.get("author")
        if not video_id or not title or not author:
            logger.warning(f"無法觸發自動播放，因為缺少 video_id、title 或 author。")
            return

        # 建立一個包含當前歌曲和佇列中所有歌曲ID的集合，以供排除
        exclude_ids = {s.get('video_id') for s in queue_snapshot if s.get('video_id')}
        if state.current_song and state.current_song.get('video_id'):
            exclude_ids.add(state.current_song.get('video_id'))

        related_videos, error = await self.youtube.get_related_videos(
            video_id, title, author, interaction, limit=needed, exclude_ids=exclude_ids
        )
        if error:
            logger.warning(f"無法獲取推薦影片: {error}")
            return

        if related_videos:
            logger.info(f"成功獲取 {len(related_videos)} 首推薦影片，正在加入佇列。")
            # --- 新增的修復程式碼 ---
            for video in related_videos:
                video['added_by'] = self.bot.user.id
            # --- 修復結束 ---
            
            for video in related_videos:
                await self.queue_manager.add_to_queue(guild_id, video)
            
            await self.queue_manager.enforce_autoplay_limit(guild_id)

    def _get_guild_folder(self, guild_id: int) -> tuple:
        """Get guild queue and folder"""
        return self.queue_manager.get_guild_queue_and_folder(guild_id)

    # --- Callback Getters ---
    def get_queue_manager(self) -> QueueManager:
        return self.queue_manager

    def get_state_manager(self) -> StateManager:
        return self.state_manager

    def get_voice_client(self, guild_id: int) -> Optional[discord.VoiceClient]:
        guild = self.bot.get_guild(guild_id)
        return guild.voice_client if guild else None

    def get_lang_manager(self) -> Optional[LanguageManager]:
        return self.lang_manager

    # --- Callback Handlers ---
    async def handle_previous(self, interaction: discord.Interaction):
        voice_client = self.get_voice_client(interaction.guild.id)
        if not voice_client:
            await interaction.response.send_message(self.lang_manager.translate(str(interaction.guild.id), "system", "music", "controls", "no_music"), ephemeral=True)
            return

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            view = self.ui_manager.get_current_view(interaction.guild.id)
            if view:
                await view.update_embed(
                    interaction,
                    self.lang_manager.translate(str(interaction.guild.id), "system", "music", "controls", "previous", user=interaction.user.name)
                )

    async def handle_toggle_playback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        voice_client = self.get_voice_client(guild_id)
        view = self.ui_manager.get_current_view(guild_id)
        if not voice_client or not view:
            return

        if voice_client.is_playing():
            voice_client.pause()
            view.stop_progress_updater()
            await self._start_disconnect_timer(guild_id)
            await view.update_embed(interaction, self.lang_manager.translate(str(guild_id), "system", "music", "controls", "paused", user=interaction.user.name))
        elif voice_client.is_paused():
            voice_client.resume()
            await self._cancel_disconnect_timer(guild_id)
            state = self.state_manager.get_state(guild_id)
            if state.current_song:
                view.start_progress_updater(state.current_song["duration"])
            await view.update_embed(interaction, self.lang_manager.translate(str(guild_id), "system", "music", "controls", "resumed", user=interaction.user.name))
        
        await view.update_button_state()

    async def handle_skip(self, interaction: discord.Interaction):
        voice_client = self.get_voice_client(interaction.guild.id)
        if not voice_client:
            await interaction.response.send_message(self.lang_manager.translate(str(interaction.guild.id), "system", "music", "controls", "no_music"), ephemeral=True)
            return
        
        view = self.ui_manager.get_current_view(interaction.guild.id)
        if view:
            view.stop_progress_updater()

        voice_client.stop()
        
        if view:
            await view.update_embed(interaction, self.lang_manager.translate(str(interaction.guild.id), "system", "music", "controls", "skipped", user=interaction.user.name))
            await view.update_button_state()

        # Check and trigger autoplay after skipping
        state = self.state_manager.get_state(interaction.guild.id)
        if state.autoplay:
            # 使用 create_task 在背景觸發自動播放，避免阻塞當前的 skip 操作
            asyncio.create_task(self._trigger_autoplay(interaction, interaction.guild.id))

    async def handle_stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        voice_client = self.get_voice_client(guild_id)

        if not voice_client:
            await interaction.response.send_message(self.lang_manager.translate(str(guild_id), "system", "music", "controls", "no_music"), ephemeral=True)
            return

        await self._cancel_disconnect_timer(guild_id)
        await self._cleanup_voice_session(guild_id)
        
        # Send a final confirmation message
        stopped_text = self.lang_manager.translate(str(guild_id), "system", "music", "controls", "stopped", user=interaction.user.name)
        embed = discord.Embed(title=f"{stopped_text}", color=discord.Color.red())
        
        # Check if the interaction is already responded to
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def handle_toggle_mode(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        current_mode = self.queue_manager.get_play_mode(guild_id)
        
        mode_order = ["no_loop", "loop_queue", "loop_single"]
        current_index = mode_order.index(current_mode.value)
        next_mode_str = mode_order[(current_index + 1) % len(mode_order)]
        
        self.queue_manager.set_play_mode(guild_id, PlayMode(next_mode_str))
        
        mode_name = self.lang_manager.translate(str(guild_id), "commands", "mode", "choices", next_mode_str)
        
        view = self.ui_manager.get_current_view(guild_id)
        if view:
            await view.update_button_state()
            await view.update_embed(interaction, self.lang_manager.translate(str(guild_id), "system", "music", "controls", "mode_changed", user=interaction.user.name, mode=mode_name))

    async def handle_toggle_shuffle(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        is_shuffle = self.queue_manager.toggle_shuffle(guild_id)
        status_key = "enabled" if is_shuffle else "disabled"
        status = self.lang_manager.translate(str(guild_id), "commands", "shuffle", "responses", status_key)
        
        view = self.ui_manager.get_current_view(guild_id)
        if view:
            await view.update_button_state()
            await view.update_embed(interaction, self.lang_manager.translate(str(guild_id), "system", "music", "controls", "shuffle_toggled", user=interaction.user.name, status=status))

    async def handle_show_queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        view = self.ui_manager.get_current_view(guild_id)
        if not view or not view.current_embed:
            await interaction.response.send_message(self.lang_manager.translate(str(guild_id), "system", "music", "controls", "update_failed"), ephemeral=True)
            return

        queue_text = await self.get_queue_text(guild_id)
        view.current_embed.set_field_at(4, name=self.lang_manager.translate(str(guild_id), "system", "music", "player", "queue"), value=queue_text, inline=False)
        await view.update_embed(interaction, view.current_embed.title, view.current_embed.color)

    async def handle_toggle_autoplay(self, interaction: discord.Interaction):
        """切換自動播放模式"""
        guild_id = interaction.guild.id
        state = self.state_manager.get_state(guild_id)
        state.autoplay = not state.autoplay
        self.state_manager.update_state(guild_id, autoplay=state.autoplay)
        logger.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, Autoplay 狀態切換為: {state.autoplay}")

        view = self.ui_manager.get_current_view(guild_id)
        if view:
            await view.update_button_state()

        status_key = "enabled" if state.autoplay else "disabled"
        status_str = self.lang_manager.translate(str(guild_id), "system", "music", "autoplay", status_key)
        
        title = self.lang_manager.translate(str(guild_id), "system", "music", "autoplay", "toggled", status=status_str)
        
        await interaction.response.send_message(f"✅ | {title}", ephemeral=True, delete_after=5)

        # If autoplay is enabled, check if the upcoming queue is empty to fill it
        if state.autoplay and len(self.queue_manager.get_queue_snapshot(interaction.guild.id)) == 0:
            logger.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, Autoplay 已啟用且待播清單為空，立即觸發推薦填充。")
            self.bot.loop.create_task(self._fill_autoplay_queue(interaction))

        # If autoplay is enabled and nothing is playing, start it
        voice_client = interaction.guild.voice_client
        if state.autoplay and not (voice_client and voice_client.is_playing()):
            logger.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, 觸發閒置時的 Autoplay。")
            self.bot.loop.create_task(self.play_next(interaction))

    async def get_queue_text(self, guild_id: int) -> str:
        """Generates the text for the queue display."""
        guild_id_str = str(guild_id)
        state = self.state_manager.get_state(guild_id)
        
        queue_items = self.queue_manager.get_queue_snapshot(guild_id)
        
        text = ""
        if state.current_song:
            minutes, seconds = divmod(float(state.current_song.get("duration", 0)), 60)
            prefix = self.lang_manager.translate(guild_id_str, "system", "music", "controls", "now_playing_prefix")
            text += f"{prefix} {state.current_song['title']} | {int(minutes):02d}:{int(seconds):02d}\n\n"
        
        if queue_items:
            label = self.lang_manager.translate(guild_id_str, "system", "music", "controls", "queue_songs")
            text += f"{label}\n"
            for i, item in enumerate(queue_items, 1):
                duration = item.get("duration", 0)
                minutes, seconds = divmod(float(duration), 60)
                text += f"{i}. {item['title']} | {int(minutes):02d}:{int(seconds):02d}\n"
        
        return text if text.strip() else self.lang_manager.translate(guild_id_str, "system", "music", "player", "queue_empty")

    async def _fill_autoplay_queue(self, interaction: discord.Interaction):
        """Fills the queue with recommended songs when autoplay is on."""
        guild_id = interaction.guild.id
        state = self.state_manager.get_state(guild_id)
        
        song_to_recommend_from = state.current_song or state.last_played_song
        if song_to_recommend_from:
            video_id = song_to_recommend_from.get("video_id")
            title = song_to_recommend_from.get("title")
            author = song_to_recommend_from.get("author")
            if video_id and title and author:
                related_videos, error = await self.youtube.get_related_videos(
                    video_id, title, author, interaction, limit=5, exclude_ids=set()
                )
                if related_videos:
                    logger.info(f"成功獲取 {len(related_videos)} 首推薦影片，正在加入佇列。")
                    # --- 新增的修復程式碼 ---
                    for video in related_videos:
                        video['added_by'] = self.bot.user.id
                    # --- 修復結束 ---

                    for video in related_videos:
                        await self.queue_manager.add_to_queue(guild_id, video)

                    # Notify user that songs have been added
                    channel = interaction.channel
                    if channel:
                        embed = discord.Embed(
                            title=f"🎶 | 已自動為您加入 {len(related_videos)} 首推薦歌曲",
                            color=discord.Color.blue()
                        )
                        await channel.send(embed=embed, delete_after=15)
                else:
                    logger.warning(f"無法獲取推薦影片: {error}")

    async def _cleanup_voice_session(self, guild_id: int):
        """Cleans up the voice session for a guild."""
        voice_client = self.get_voice_client(guild_id)
        state = self.state_manager.get_state(guild_id)

        # Stop playback and disconnect
        if voice_client:
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            if voice_client.is_connected():
                await voice_client.disconnect()

        # Clean up all UI messages
        for message in state.ui_messages:
            try:
                await message.delete()
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
        
        # Clean up the view
        await self.ui_manager.cleanup_view(guild_id)

        # Clear queue and state
        self.queue_manager.clear_queue(guild_id)
        self.state_manager.update_state(guild_id, current_song=None, last_played_song=None, current_message=None, current_view=None, ui_messages=[])
        logger.info(f"[音樂] 伺服器 ID: {guild_id}, 已清理語音會話。")

    async def _cancel_disconnect_timer(self, guild_id: int):
        """Cancels the disconnect timer for a guild."""
        if guild_id in self.disconnect_timers:
            self.disconnect_timers[guild_id].cancel()
            del self.disconnect_timers[guild_id]
            logger.info(f"[音樂] 伺服器 ID: {guild_id}, 已取消閒置斷線計時器。")

    async def _start_disconnect_timer(self, guild_id: int):
        """Starts the disconnect timer for a guild."""
        await self._cancel_disconnect_timer(guild_id) # Cancel any existing timer
        
        logger.info(f"[音樂] 伺服器 ID: {guild_id}, 播放器已暫停，啟動 5 分鐘閒置斷線計時器。")
        self.disconnect_timers[guild_id] = self.bot.loop.create_task(
            self._disconnect_after_delay(guild_id)
        )

    async def _disconnect_after_delay(self, guild_id: int):
        """Disconnects the bot after a 5-minute delay if it's still paused."""
        await asyncio.sleep(300) # 5 minutes
        
        voice_client = self.get_voice_client(guild_id)
        if voice_client and voice_client.is_connected() and voice_client.is_paused():
            logger.info(f"[音樂] 伺服器 ID: {guild_id}, 閒置超過 5 分鐘，自動斷線。")
            
            # Find a channel to send the message
            state = self.state_manager.get_state(guild_id)
            channel = None
            if state.current_message:
                channel = state.current_message.channel
            
            await self._cleanup_voice_session(guild_id)
            
            if channel:
                idle_disconnect_msg = self.lang_manager.translate(str(guild_id), "system", "music", "status", "idle_disconnect")
                embed = discord.Embed(title=f"😴 | {idle_disconnect_msg}", color=discord.Color.orange())
                try:
                    await channel.send(embed=embed, delete_after=60)
                except discord.errors.Forbidden:
                    logger.warning(f"[音樂] 伺服器 ID: {guild_id}, 無法發送閒置斷線訊息（權限不足）。")
        else:
            logger.info(f"[音樂] 伺服器 ID: {guild_id}, 閒置斷線計時器觸發，但機器人已非暫停狀態，取消操作。")

        # Clean up the timer task from the dictionary
        if guild_id in self.disconnect_timers:
            del self.disconnect_timers[guild_id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state changes, including auto-pause and auto-disconnect."""
        # Ignore bot's own state changes unless it's a disconnect
        if member.id == self.bot.user.id:
            if before.channel is not None and after.channel is None:
                # Bot was disconnected
                guild_id = member.guild.id
                logger.info(f"[音樂] 偵測到機器人被動斷線於伺服器 {member.guild.name}。")
                await self._cancel_disconnect_timer(guild_id)
                await self._cleanup_voice_session(guild_id)
            return

        # Check the voice channel the bot is in
        voice_client = member.guild.voice_client
        if not voice_client or not voice_client.channel:
            return

        # Check if the state change happened in the bot's channel
        if before.channel == voice_client.channel or after.channel == voice_client.channel:
            # Get the number of human members in the channel
            human_members = [m for m in voice_client.channel.members if not m.bot]
            
            if not human_members:
                # No one left, pause the player and start disconnect timer
                if voice_client.is_playing():
                    logger.info(f"[音樂] 伺服器 ID: {member.guild.id}, 頻道內無人，自動暫停播放。")
                    voice_client.pause()
                    await self._start_disconnect_timer(member.guild.id)
                    
                    # Update UI if possible
                    view = self.ui_manager.get_current_view(member.guild.id)
                    if view:
                        view.stop_progress_updater()
                        # We can't send an interaction here, but we can update the buttons
                        await view.update_button_state()

            else:
                # Someone is in the channel, resume if paused
                if voice_client.is_paused():
                    # Check if the pause was due to inactivity (i.e., a timer is running)
                    if member.guild.id in self.disconnect_timers:
                        logger.info(f"[音樂] 伺服器 ID: {member.guild.id}, 有使用者加入，自動恢復播放。")
                        voice_client.resume()
                        await self._cancel_disconnect_timer(member.guild.id)
                        
                        # Update UI
                        view = self.ui_manager.get_current_view(member.guild.id)
                        if view:
                            state = self.state_manager.get_state(member.guild.id)
                            if state.current_song:
                                view.start_progress_updater(state.current_song["duration"])
                            await view.update_button_state()

    async def _create_dummy_interaction(self, channel, guild, original_interaction):
        """Creates a dummy interaction object for internal use."""
        
        class DummyUser:
            def __init__(self, original_user):
                self.name = original_user.name
                self.display_name = original_user.display_name
                self.id = original_user.id
                self.mention = original_user.mention
                self.display_avatar = original_user.display_avatar
                self.avatar = type('Avatar', (), {'url': original_user.display_avatar.url})()
            def __getattr__(self, name):
                return getattr(original_interaction.user, name)

        class DummyInteraction:
            def __init__(self, channel, guild, user):
                self.channel = channel
                self.guild = guild
                self.user = user
                self.application_id = original_interaction.application_id
                self.id = original_interaction.id
                
                class DummyResponse:
                    def __init__(self):
                        self.is_done = lambda: True
                    async def send_message(self, *args, **kwargs):
                        return await channel.send(*args, **kwargs)
                self.response = DummyResponse()

                class DummyFollowup:
                    def __init__(self, channel):
                        self._channel = channel
                    async def send(self, *args, **kwargs):
                        return await channel.send(*args, **kwargs)
                self.followup = DummyFollowup(channel)

        return DummyInteraction(channel, guild, DummyUser(original_interaction.user))


    async def _player_loop(self, interaction: discord.Interaction, song: dict):
        """Monitors the player and handles song completion."""
        guild_id = interaction.guild.id
        logger.info(f"[{guild_id}] Player loop started for '{song['title']}'.")
        
        await asyncio.sleep(2) # Wait for playback to start
        
        while True:
            voice_client = self.get_voice_client(guild_id)
            if not voice_client or not voice_client.is_connected():
                logger.warning(f"[{guild_id}] Player loop exiting: voice client disconnected.")
                return

            if voice_client.is_paused():
                await asyncio.sleep(1)
                continue

            if not voice_client.is_playing():
                logger.info(f"[{guild_id}] Player loop detected song has finished.")
                break
            
            await asyncio.sleep(1)
        
        state = self.state_manager.get_state(guild_id)
        # Ensure we are still on the same song before triggering after_play
        if state.current_song and state.current_song['video_id'] == song['video_id']:
            logger.info(f"[{guild_id}] 歌曲 '{song['title']}' 播放完畢，觸發 _handle_after_play。")
            # Use a new interaction object to avoid issues with expired interactions
            channel = interaction.channel
            if channel:
                new_interaction = await self._create_dummy_interaction(channel, interaction.guild, interaction)
                await self._handle_after_play(new_interaction, song)
        else:
            logger.info(f"[{guild_id}] Player loop for '{song['title']}' exiting without action. (Song might have been skipped).")

async def setup(bot):
    """Initialize the music cog"""
    cog = YTMusic(bot)
    await cog.setup_hook()  # Initialize async components
    await bot.add_cog(cog)
