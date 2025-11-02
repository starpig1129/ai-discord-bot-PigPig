import asyncio
import discord
import logging as logger
from typing import Optional, Dict, Any
from .ui.controls import MusicControlView
from .ui.progress import ProgressDisplay
from cogs.language_manager import LanguageManager

class UIManager:
    def __init__(self, bot=None):
        self.views: Dict[int, MusicControlView] = {}
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None
        
    def _get_lang_manager(self):
        """Get language manager instance"""
        if not self.lang_manager and self.bot:
            self.lang_manager = self.bot.get_cog("LanguageManager")
        return self.lang_manager
        
    def _translate_music(self, guild_id: str, *path, **kwargs) -> str:
        """音樂模組專用翻譯方法"""
        lang_manager = self._get_lang_manager()
        if not lang_manager:
            # 備用機制
            return self._get_fallback_text(path[-1], **kwargs)
        
        return lang_manager.translate(guild_id, "system", "music", *path, **kwargs)
        
    def _get_fallback_text(self, key: str, **kwargs) -> str:
        """翻譯失敗時的備用文字"""
        fallback_texts = {
            "now_playing": "🎵 正在播放",
            "uploader": "👤 上傳頻道",
            "duration": "⏱️ 播放時長",
            "views": "👀 觀看次數",
            "progress": "🎵 播放進度",
            "queue": "📜 播放清單",
            "queue_empty": "清單為空",
            "added_by": "由 {user} 添加"
        }
        
        text = fallback_texts.get(key, key)
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
        
    def get_current_view(self, guild_id: int) -> Optional[MusicControlView]:
        return self.views.get(guild_id)

    async def update_player_ui(self, interaction: discord.Interaction, track: wavelink.Track,
                             current_message: Optional[discord.Message], music_cog) -> discord.Message:
        """Update or create the music player UI"""
        try:
            guild_id = interaction.guild.id
            guild_id_str = str(guild_id)
            embed = self._create_player_embed(track, guild_id_str)

            callbacks = {
                "previous_callback": music_cog.handle_previous,
                "toggle_playback_callback": music_cog.handle_toggle_playback,
                "skip_callback": music_cog.handle_skip,
                "stop_callback": music_cog.handle_stop,
                "toggle_mode_callback": music_cog.handle_toggle_mode,
                "toggle_shuffle_callback": music_cog.handle_toggle_shuffle,
                "show_queue_callback": music_cog.handle_show_queue,
                "toggle_autoplay_callback": music_cog.handle_toggle_autoplay,
                "get_voice_client": lambda: music_cog.get_voice_client(guild_id),
                "get_lang_manager": music_cog.get_lang_manager,
            }

            if guild_id in self.views:
                old_view = self.views[guild_id]
                old_view.stop_progress_updater()

            view = MusicControlView(interaction, song_info=track, **callbacks)
            self.views[guild_id] = view

            state = music_cog.state_manager.get_state(guild_id)
            
            for old_message in state.ui_messages:
                try:
                    await old_message.delete()
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    pass
            state.ui_messages.clear()

            message = await interaction.channel.send(embed=embed, view=view)
            
            if not message:
                raise RuntimeError("Failed to send the new player message.")

            state.current_message = message
            state.ui_messages.append(message)
            
            view.message = message
            view.current_embed = embed
            
            await view.update_button_state()
            
            if not track.is_stream:
                view.start_progress_updater(track.length / 1000)
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to update player UI: {e}")
            raise

    def _create_player_embed(self, track: wavelink.Track, guild_id: str = None) -> discord.Embed:
        """Create the player embed with song information"""
        if guild_id:
            title_text = self._translate_music(guild_id, "player", "now_playing")
            uploader_text = self._translate_music(guild_id, "player", "uploader")
            duration_text = self._translate_music(guild_id, "player", "duration")
            progress_text = self._translate_music(guild_id, "player", "progress")
            queue_text = self._translate_music(guild_id, "player", "queue")
            queue_empty_text = self._translate_music(guild_id, "player", "queue_empty")
            added_by_text = self._translate_music(guild_id, "player", "added_by", user=track.extras.requester.name)
        else:
            # Fallback
            title_text = self._get_fallback_text("now_playing")
            uploader_text = self._get_fallback_text("uploader")
            duration_text = self._get_fallback_text("duration")
            progress_text = self._get_fallback_text("progress")
            queue_text = self._get_fallback_text("queue")
            queue_empty_text = self._get_fallback_text("queue_empty")
            added_by_text = self._get_fallback_text("added_by", user=track.extras.requester.name)
        
        embed = discord.Embed(
            title=title_text,
            description=f"**[{track.title}]({track.uri})**",
            color=discord.Color.blue()
        )
        
        embed.add_field(name=uploader_text, value=track.author, inline=True)

        if track.is_stream:
            live_text = self._translate_music(guild_id, "player", "live")
            embed.add_field(name=duration_text, value=f"**{live_text}** 🔴", inline=True)
        else:
            minutes, seconds = divmod(track.length / 1000, 60)
            embed.add_field(name=duration_text, value=f"{int(minutes):02d}:{int(seconds):02d}", inline=True)

        if not track.is_stream:
            progress_bar = ProgressDisplay.create_progress_bar(0, track.length / 1000)
            embed.add_field(name=progress_text, value=progress_bar, inline=False)
        
        if hasattr(track, 'views'):
             views_text = self._translate_music(guild_id, "player", "views")
             embed.add_field(name=views_text, value=f"{track.views:,}", inline=True)

        embed.add_field(name=queue_text, value=queue_empty_text, inline=False)
        
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        
        embed.set_footer(text=added_by_text, icon_url=track.extras.requester.display_avatar.url)
        
        return embed
        
            
    async def cleanup_view(self, guild_id: int):
        """Clean up the view for a specific guild."""
        if guild_id in self.views:
            view = self.views.pop(guild_id)
            view.stop_progress_updater()
