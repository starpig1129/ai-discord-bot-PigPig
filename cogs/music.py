import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import logging as logger
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from addons.settings import Settings
from .music_lib.youtube import YouTubeManager
from .music_lib.audio_manager import AudioManager
from .music_lib.state_manager import StateManager
from .music_lib.queue_manager import QueueManager, PlayMode
from .music_lib.ui_manager import UIManager
from .music_lib.ui.song_select import SongSelectView
from cogs.language_manager import LanguageManager # Import LanguageManager

class YTMusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.youtube = None  # Will be initialized in setup_hook
        self._executor = ThreadPoolExecutor(max_workers=3)
        self.settings = Settings()
        
        # Initialize managers
        self.audio_manager = AudioManager()
        self.state_manager = StateManager()
        self.queue_manager = QueueManager()
        self.ui_manager = UIManager(bot)
        self.lang_manager: Optional[LanguageManager] = None # Initialize lang_manager

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
        guild_id = str(interaction.guild.id)
        if not self.lang_manager: # Ensure lang_manager is loaded
             self.lang_manager = self.bot.get_cog("LanguageManager")
             if not self.lang_manager:
                 await interaction.response.send_message("Language manager not loaded.", ephemeral=True)
                 return

        # Localize choices (name is already localized by decorator, but value needs translation for response)
        mode_value = mode.value
        mode_name = self.lang_manager.translate(guild_id, "commands", "mode", "choices", mode_value)

        self.queue_manager.set_play_mode(interaction.guild.id, PlayMode(mode_value))

        title = self.lang_manager.translate(guild_id, "commands", "mode", "responses", "success", mode=mode_name)
        embed = discord.Embed(title=f"✅ | {title}", color=discord.Color.blue())
        message = await interaction.response.send_message(embed=embed)
        state = self.state_manager.get_state(interaction.guild.id)
        state.ui_messages.append(message)

    @app_commands.command(name="shuffle", description="切換隨機播放")
    async def shuffle(self, interaction: discord.Interaction):
        """隨機播放命令"""
        guild_id = str(interaction.guild.id)
        if not self.lang_manager: # Ensure lang_manager is loaded
             self.lang_manager = self.bot.get_cog("LanguageManager")
             if not self.lang_manager:
                 await interaction.response.send_message("Language manager not loaded.", ephemeral=True)
                 return

        is_shuffle = self.queue_manager.toggle_shuffle(interaction.guild.id)
        status_key = "enabled" if is_shuffle else "disabled"
        status = self.lang_manager.translate(guild_id, "commands", "shuffle", "responses", status_key)
        title = self.lang_manager.translate(guild_id, "commands", "shuffle", "responses", "success", status=status)
        embed = discord.Embed(title=f"✅ | {title}", color=discord.Color.blue())
        message = await interaction.response.send_message(embed=embed)
        state = self.state_manager.get_state(interaction.guild.id)
        state.ui_messages.append(message)


    @app_commands.command(name="play", description="播放影片(網址或關鍵字)")
    async def play(self, interaction: discord.Interaction, query: str = ""):
        """播放音樂命令"""
        # 檢查使用者是否已在語音頻道
        if interaction.user.voice:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:
                await channel.connect()
        else:
            guild_id = str(interaction.guild.id)
            if not self.lang_manager: # Ensure lang_manager is loaded
                 self.lang_manager = self.bot.get_cog("LanguageManager")
                 if not self.lang_manager:
                     await interaction.response.send_message("Language manager not loaded.", ephemeral=True)
                     return
            title = self.lang_manager.translate(guild_id, "commands", "play", "errors", "no_voice_channel")
            embed = discord.Embed(title=f"❌ | {title}", color=discord.Color.red())
            message = await interaction.response.send_message(embed=embed)
            state = self.state_manager.get_state(interaction.guild.id)
            state.ui_messages.append(message)
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
        guild_id = str(interaction.guild.id)
        _, folder = self._get_guild_folder(guild_id)
        video_infos, error = await self.youtube.download_playlist(url, folder, interaction)
        
        if error:
            title = self.lang_manager.translate(guild_id, "commands", "play", "errors", "playlist_download_failed", error=error)
            embed = discord.Embed(title=f"❌ | {title}", color=discord.Color.red())
            message = await interaction.followup.send(embed=embed)
            # Track error message
            state = self.state_manager.get_state(guild_id)
            state.ui_messages.append(message)
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
        title = self.lang_manager.translate(guild_id, "commands", "play", "responses", "playlist_added", count=len(added_songs), total=len(video_infos))
        embed = discord.Embed(
            title=f"✅ | {title}",
            description=description,
            color=discord.Color.blue()
        )
        message = await interaction.followup.send(embed=embed)
        # Track playlist message
        state = self.state_manager.get_state(guild_id)
        state.ui_messages.append(message)

    async def _handle_single_video(self, interaction: discord.Interaction, url: str) -> bool:
        """Handle single video URL"""
        guild_id = interaction.guild.id
        guild_id_str = str(guild_id)
        queue = self.queue_manager.get_queue(guild_id)
        state = self.state_manager.get_state(guild_id)
        
        if queue.qsize() >= 5:
            title = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "queue_full_title")
            desc = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "queue_full_desc")
            embed = discord.Embed(
                title=f"❌ | {title}",
                description=desc,
                color=discord.Color.red()
            )
            message = await interaction.followup.send(embed=embed)
            state.ui_messages.append(message)
            return False
            
        _, folder = self._get_guild_folder(guild_id)
        should_download = queue.qsize() == 0
        
        if should_download:
            video_info, error = await self.youtube.download_audio(url, folder, interaction)
        else:
            video_info, error = await self.youtube.get_video_info_without_download(url, interaction)
            
        if error:
            title = self.lang_manager.translate(guild_id_str, "commands", "play", "errors", "video_info_failed", error=error)
            embed = discord.Embed(title=f"❌ | {title}", color=discord.Color.red())
            message = await interaction.followup.send(embed=embed)
            state.ui_messages.append(message)
            return False
            
        await self.queue_manager.add_to_queue(guild_id, video_info)
        title = self.lang_manager.translate(guild_id_str, "commands", "play", "responses", "song_added", title=video_info['title'])
        embed = discord.Embed(title=f"✅ | {title}", color=discord.Color.blue())
        message = await interaction.followup.send(embed=embed)
        state.ui_messages.append(message)
        return True

    async def _handle_search(self, interaction: discord.Interaction, query: str):
        """Handle search query"""
        results = await self.youtube.search_videos(query)
        guild_id = str(interaction.guild.id)
        if not results:
            title = self.lang_manager.translate(guild_id, "commands", "play", "errors", "no_results")
            embed = discord.Embed(title=f"❌ | {title}", color=discord.Color.red())
            message = await interaction.followup.send(embed=embed)
            # Track error message
            state = self.state_manager.get_state(guild_id)
            state.ui_messages.append(message)
            return
        
        # Format durations properly
        formatted_results = []
        for i, result in enumerate(results, 1):
            duration_secs = result.get('duration', 0)
            minutes, seconds = divmod(duration_secs, 60)
            duration_str = f"{int(minutes):02d}:{int(seconds):02d}"
            formatted_results.append(f"{i}. {result['title']} ({duration_str})")

        view = SongSelectView(self, results, interaction)
        desc_prefix = self.lang_manager.translate(guild_id, "commands", "play", "responses", "select_song")
        description = f"{desc_prefix}\n\n" + "\n".join(formatted_results)
        embed_title = self.lang_manager.translate(guild_id, "commands", "play", "responses", "search_results_title")
        embed = discord.Embed(
            title=f"🔍 | {embed_title}",
            description=description,
            color=discord.Color.blue()
        )
        
        # Get state for message tracking
        state = self.state_manager.get_state(interaction.guild.id)
        
        try:
            message = await interaction.followup.send(embed=embed, view=view)
        except discord.errors.HTTPException as e:
            if e.code == 50027:  # Invalid Webhook Token
                message = await interaction.channel.send(embed=embed, view=view)
            else:
                logger.error(f"Failed to send search results: {e}")
                raise
        
        # Track search results message
        if message:
            state.ui_messages.append(message)

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
                self.state_manager.update_state(guild_id, current_message=None)
                return
                
            # Update state and play song
            self.state_manager.update_state(guild_id, current_song=next_song)
            await self._play_song(interaction, next_song, voice_client)
            
        except Exception as e:
            logger.error(f"[音樂] 伺服器 ID： {guild_id}, 播放音樂時出錯： {e}")
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
            
            file_path = state.current_song["file_path"]
            audio_source = self.audio_manager.create_audio_source(file_path)
            
            message = await self.ui_manager.update_player_ui(
                interaction, 
                state.current_song,
                state.current_message,
                self.youtube,
                music_cog=self
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
            self.queue_manager.set_queue(guild_id, new_queue)

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
            music_cog=self
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
        guild_id_str = str(guild_id)
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
                        # Add response attribute
                        class DummyResponse:
                            def __init__(self):
                                self.is_done = lambda: True
                            async def send_message(self, *args, **kwargs):
                                return await channel.send(*args, **kwargs)
                        
                        self.response = DummyResponse()
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
                            logger.error(f"[音樂] 重試播放失敗： {str(retry_error)}")
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
                                logger.error(f"[音樂] 發送錯誤訊息失敗： {str(final_error)}")
            
        except Exception as e:
            logger.error(f"[音樂] 處理播放完成時出錯： {str(e)}")

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
        voice_client = self.get_voice_client(interaction.guild.id)
        view = self.ui_manager.get_current_view(interaction.guild.id)
        if not voice_client or not view:
            return

        if voice_client.is_playing():
            voice_client.pause()
            view.stop_progress_updater()
            await view.update_embed(interaction, self.lang_manager.translate(str(interaction.guild.id), "system", "music", "controls", "paused", user=interaction.user.name))
        elif voice_client.is_paused():
            voice_client.resume()
            state = self.state_manager.get_state(interaction.guild.id)
            if state.current_song:
                view.start_progress_updater(state.current_song["duration"])
            await view.update_embed(interaction, self.lang_manager.translate(str(interaction.guild.id), "system", "music", "controls", "resumed", user=interaction.user.name))
        
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

    async def handle_stop(self, interaction: discord.Interaction):
        voice_client = self.get_voice_client(interaction.guild.id)
        if not voice_client:
            return

        view = self.ui_manager.get_current_view(interaction.guild.id)
        if view:
            await view.update_embed(interaction, self.lang_manager.translate(str(interaction.guild.id), "system", "music", "controls", "stopped", user=interaction.user.name), discord.Color.red())

        self.queue_manager.clear_queue(interaction.guild.id)
        if voice_client.is_connected():
            voice_client.stop()
            await voice_client.disconnect()

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

    async def get_queue_text(self, guild_id: int) -> str:
        """Generates the text for the queue display."""
        guild_id_str = str(guild_id)
        queue = self.queue_manager.get_queue(guild_id)
        state = self.state_manager.get_state(guild_id)
        
        queue_items = self.queue_manager.get_queue_snapshot(guild_id)
        
        text = ""
        if state.current_song:
            minutes, seconds = divmod(float(state.current_song["duration"]), 60)
            prefix = self.lang_manager.translate(guild_id_str, "system", "music", "controls", "now_playing_prefix")
            text += f"{prefix} {state.current_song['title']} | {int(minutes):02d}:{int(seconds):02d}\n\n"
        
        if queue_items:
            label = self.lang_manager.translate(guild_id_str, "system", "music", "controls", "queue_songs")
            text += f"{label}\n"
            for i, item in enumerate(queue_items, 1):
                minutes, seconds = divmod(float(item["duration"]), 60)
                text += f"{i}. {item['title']} | {int(minutes):02d}:{int(seconds):02d}\n"
        
        return text if text else self.lang_manager.translate(guild_id_str, "system", "music", "player", "queue_empty")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle bot leaving voice channel"""
        if member.id == self.bot.user.id and before.channel is not None and after.channel is None:
            guild_id = member.guild.id
            _, folder = self._get_guild_folder(guild_id)
            
            await self.ui_manager.cleanup_view(guild_id)
            
            state = self.state_manager.get_state(guild_id)
            for message in state.ui_messages:
                try:
                    await message.delete()
                except:
                    pass
            
            await self.audio_manager.cleanup_guild_files(guild_id, folder)
            self.queue_manager.clear_guild_data(guild_id)
            self.state_manager.clear_state(guild_id)
            
            logger.info(f"[音樂] 伺服器 ID： {member.guild.name}, 離開語音頻道並清理資源")

async def setup(bot):
    """Initialize the music cog"""
    cog = YTMusic(bot)
    await cog.setup_hook()  # Initialize async components
    await bot.add_cog(cog)
