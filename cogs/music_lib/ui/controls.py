import discord
import asyncio
import logging as logger
from typing import Optional
from .progress import ProgressDisplay
from cogs.language_manager import LanguageManager
from ..queue_manager import PlayMode

class MusicControlView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, *,
                 song_info: dict,  # Add song_info
                 previous_callback, toggle_playback_callback, skip_callback, stop_callback,
                 toggle_mode_callback, toggle_shuffle_callback, show_queue_callback,
                 get_queue_manager, get_state_manager, get_voice_client, get_lang_manager):
        super().__init__(timeout=None)
        self.guild = interaction.guild
        self.message = None
        self.current_embed = None
        self.song_info = song_info  # Store song_info
        self.lang_manager: Optional[LanguageManager] = None
        self._is_updating = False
        self.update_task = None
        self.current_position = 0

        # Action Callbacks
        self.previous_callback = previous_callback
        self.toggle_playback_callback = toggle_playback_callback
        self.skip_callback = skip_callback
        self.stop_callback = stop_callback
        self.toggle_mode_callback = toggle_mode_callback
        self.toggle_shuffle_callback = toggle_shuffle_callback
        self.show_queue_callback = show_queue_callback

        # State/Manager Getters
        self.get_queue_manager = get_queue_manager
        self.get_state_manager = get_state_manager
        self.get_voice_client = get_voice_client
        self.get_lang_manager = get_lang_manager

        asyncio.create_task(self.update_button_state(update_message=False))

    def _get_lang_manager(self):
        """Get language manager instance"""
        if not self.lang_manager:
            self.lang_manager = self.get_lang_manager()
        return self.lang_manager
        
    def _translate_music(self, *path, **kwargs) -> str:
        """音樂模組專用翻譯方法"""
        lang_manager = self._get_lang_manager()
        if not lang_manager:
            return self._get_fallback_text(path[-1], **kwargs)
        
        return lang_manager.translate(str(self.guild.id), "system", "music", *path, **kwargs)
        
    def _get_fallback_text(self, key: str, **kwargs) -> str:
        """備用文字機制"""
        fallback_texts = {
            "no_music": "❌ 沒有正在播放的音樂！",
            "no_songs": "❌ 沒有可播放的歌曲！",
            "previous": "⏮️ {user} 返回上一首",
            "paused": "⏸️ {user} 暫停了音樂",
            "resumed": "▶️ {user} 繼續了音樂",
            "skipped": "⏭️ {user} 跳過了音樂",
            "stopped": "⏹️ {user} 停止了播放",
            "mode_changed": "🔄 {user} 將播放模式設為 {mode}",
            "shuffle_toggled": "🔀 {user} {status}隨機播放",
            "now_playing_prefix": "▶️ 正在播放:",
            "queue_songs": "待播放歌曲:",
            "update_failed": "無法更新播放清單"
        }
        
        text = fallback_texts.get(key, key)
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
            
    def _get_mode_name(self, mode: str) -> str:
        """獲取播放模式翻譯名稱"""
        lang_manager = self._get_lang_manager()
        if lang_manager:
            return lang_manager.translate(str(self.guild.id), "commands", "mode", "choices", mode)
        
        # 備用機制
        mode_names = {
            "no_loop": "不循環",
            "loop_queue": "清單循環",
            "loop_single": "單曲循環"
        }
        return mode_names.get(mode, mode)
        
    def _get_shuffle_status(self, is_enabled: bool) -> str:
        """獲取隨機播放狀態文字"""
        lang_manager = self._get_lang_manager()
        if lang_manager:
            status_key = "enabled" if is_enabled else "disabled"
            return lang_manager.translate(str(self.guild.id), "commands", "shuffle", "responses", status_key)
        
        # 備用機制
        return "開啟" if is_enabled else "關閉"

    async def update_button_state(self, update_message: bool = True):
        """Update button states based on current playback and mode status"""
        voice_client = self.get_voice_client()
        guild_id = self.guild.id
        queue_manager = self.get_queue_manager()

        # Update button states
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                # Play/Pause button
                if child.custom_id == "toggle_playback":
                    if voice_client and voice_client.is_playing():
                        child.emoji = discord.PartialEmoji.from_str('⏸️')
                    elif voice_client and voice_client.is_paused():
                        child.emoji = discord.PartialEmoji.from_str('▶️')
                    else:
                        child.emoji = discord.PartialEmoji.from_str('⏯️')

                # Loop mode button
                elif child.custom_id == "toggle_mode":
                    mode_emojis = {
                        "no_loop": '➡️',
                        "loop_queue": '🔁',
                        "loop_single": '🔂'
                    }
                    current_mode = queue_manager.get_play_mode(guild_id).value
                    child.emoji = discord.PartialEmoji.from_str(mode_emojis[current_mode])

                # Shuffle button
                elif child.custom_id == "toggle_shuffle":
                    is_shuffle = queue_manager.is_shuffle_enabled(guild_id)
                    child.style = discord.ButtonStyle.green if is_shuffle else discord.ButtonStyle.gray
                    child.emoji = discord.PartialEmoji.from_str('🔀')

        # Only update message if requested and message exists
        if update_message and self.message:
            try:
                await self.message.edit(view=self)
            except Exception as e:
                logger.error(f"Failed to update button state: {e}")

    def start_progress_updater(self, duration: int):
        if self.update_task:
            self.update_task.cancel()
        self.current_position = 0
        self.update_task = asyncio.create_task(self.update_progress(duration))

    def stop_progress_updater(self):
        if self.update_task:
            self.update_task.cancel()
            self.update_task = None
            self._is_updating = False

    async def update_progress(self, duration):
        try:
            if self._is_updating:
                return
            
            self._is_updating = True
            await self.update_button_state()
            update_interval = 5
            last_update = 0
            message_refresh_interval = 600
            last_message_refresh = asyncio.get_event_loop().time()

            try:
                while True:
                    voice_client = self.get_voice_client()
                    if not voice_client or not voice_client.is_playing():
                        await self.update_button_state()
                        break
                    
                    self.current_position += 1
                    if self.current_position > duration:
                        await self.update_button_state()
                        break
                        
                    current_time = asyncio.get_event_loop().time()
                    
                    # Refresh message periodically
                    if current_time - last_message_refresh >= message_refresh_interval:
                        try:
                            new_message = await self.message.channel.send(embed=self.current_embed, view=self)
                            await self.message.delete()
                            self.message = new_message
                            last_message_refresh = current_time
                        except Exception as e:
                            logger.error(f"刷新訊息失敗: {e}")
                            break
                    
                    # Update progress bar
                    if current_time - last_update >= update_interval:
                        if self.current_embed and self.message:
                            try:
                                progress_bar = ProgressDisplay.create_progress_bar(self.current_position, duration)
                                self.current_embed.set_field_at(3, name="🎵 播放進度", value=progress_bar, inline=False)
                                
                                await self.message.edit(embed=self.current_embed, view=self)
                                last_update = current_time
                            except discord.errors.HTTPException as e:
                                if e.code == 50027:  # Invalid Webhook Token
                                    try:
                                        new_message = await self.message.channel.send(embed=self.current_embed, view=self)
                                        try:
                                            await self.message.delete()
                                        except discord.errors.NotFound:
                                            pass
                                        self.message = new_message
                                        last_update = current_time
                                        logger.info("Successfully recreated message in update_progress")
                                    except Exception as inner_e:
                                        logger.error(f"Failed to recreate message in update_progress: {inner_e}")
                                        break
                                else:
                                    logger.error(f"更新進度條位置失敗: {e}")
                    
                    await asyncio.sleep(1)
            finally:
                self._is_updating = False
                if hasattr(self, 'update_task'):
                    self.update_task = None
        except Exception as e:
            logger.error(f"Progress update error: {e}")
            try:
                await self.update_button_state()
            except Exception as view_error:
                logger.error(f"Failed to update button state after error: {view_error}")

    async def update_embed(self, interaction: discord.Interaction, title: str, color: discord.Color = discord.Color.blue()):
        """Update the embed with error handling and message recreation"""
        if not (self.current_embed and self.message):
            return

        self.current_embed.title = title
        self.current_embed.color = color

        async def try_edit_or_recreate(message, embed, view):
            try:
                await message.edit(embed=embed)
                return message
            except discord.errors.HTTPException as e:
                if e.code == 50027:  # Invalid Webhook Token
                    try:
                        # Create new message
                        new_message = await message.channel.send(embed=embed, view=view)
                        # Try to delete old message
                        try:
                            await message.delete()
                        except (discord.errors.NotFound, discord.errors.Forbidden):
                            pass
                        logger.info("Successfully recreated message")
                        return new_message
                    except Exception as inner_e:
                        logger.error(f"Failed to recreate message: {inner_e}")
                        return None
                else:
                    logger.error(f"Failed to update embed: {e}")
                    return None
            except Exception as e:
                logger.error(f"Unexpected error in update_embed: {e}")
                return None

        new_message = await try_edit_or_recreate(self.message, self.current_embed, self)
        if new_message:
            self.message = new_message

    @discord.ui.button(emoji='⏮️', style=discord.ButtonStyle.gray, custom_id="previous")
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.previous_callback(interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(emoji='⏯️', style=discord.ButtonStyle.gray, custom_id="toggle_playback")
    async def toggle_playback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_playback_callback(interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.gray, custom_id="skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.skip_callback(interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(emoji='⏹️', style=discord.ButtonStyle.red, custom_id="stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.stop_callback(interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(emoji='🔄', style=discord.ButtonStyle.gray, custom_id="toggle_mode")
    async def toggle_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換播放模式"""
        await self.toggle_mode_callback(interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(emoji='🔀', style=discord.ButtonStyle.gray, custom_id="toggle_shuffle")
    async def toggle_shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換隨機播放"""
        await self.toggle_shuffle_callback(interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(emoji='📜', style=discord.ButtonStyle.gray, custom_id="show_queue")
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_queue_callback(interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()
