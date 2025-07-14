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

    async def update_player_ui(self, interaction: discord.Interaction, item: Dict[str, Any],
                             current_message: Optional[discord.Message], youtube_manager, music_cog) -> discord.Message:
        """Update or create the music player UI"""
        try:
            guild_id = interaction.guild.id
            guild_id_str = str(guild_id)
            embed = self._create_player_embed(item, youtube_manager, guild_id_str)

            callbacks = {
                "previous_callback": music_cog.handle_previous,
                "toggle_playback_callback": music_cog.handle_toggle_playback,
                "skip_callback": music_cog.handle_skip,
                "stop_callback": music_cog.handle_stop,
                "toggle_mode_callback": music_cog.handle_toggle_mode,
                "toggle_shuffle_callback": music_cog.handle_toggle_shuffle,
                "show_queue_callback": music_cog.handle_show_queue,
                "get_queue_manager": music_cog.get_queue_manager,
                "get_state_manager": music_cog.get_state_manager,
                "get_voice_client": lambda: music_cog.get_voice_client(guild_id),
                "get_lang_manager": music_cog.get_lang_manager,
            }

            # 在創建新 View 之前，先停止舊 View 的背景任務
            if guild_id in self.views:
                old_view = self.views[guild_id]
                old_view.stop_progress_updater()

            view = MusicControlView(interaction, song_info=item, **callbacks)
            self.views[guild_id] = view

            state = music_cog.state_manager.get_state(guild_id)
            
            # Clean up all previous UI messages
            for old_message in state.ui_messages:
                try:
                    await old_message.delete()
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    pass
            state.ui_messages.clear()

            # Always send a new message to ensure it's at the bottom
            message = await interaction.channel.send(embed=embed, view=view)
            
            if not message:
                raise RuntimeError("Failed to send the new player message.")

            # Track the new player message
            state.current_message = message
            state.ui_messages.append(message)
            
            view.message = message
            view.current_embed = embed
            
            await view.update_button_state()
            
            view.start_progress_updater(item['duration'])
            
            return message
            
        except Exception as e:
            logger.error(f"更新播放器UI失敗: {e}")
            raise

    def _create_player_embed(self, item: Dict[str, Any], youtube_manager, guild_id: str = None) -> discord.Embed:
        """Create the player embed with song information"""
        # 使用翻譯系統獲取文字
        if guild_id:
            title_text = self._translate_music(guild_id, "player", "now_playing")
            uploader_text = self._translate_music(guild_id, "player", "uploader")
            duration_text = self._translate_music(guild_id, "player", "duration")
            views_text = self._translate_music(guild_id, "player", "views")
            progress_text = self._translate_music(guild_id, "player", "progress")
            queue_text = self._translate_music(guild_id, "player", "queue")
            queue_empty_text = self._translate_music(guild_id, "player", "queue_empty")
            added_by_text = self._translate_music(guild_id, "player", "added_by", user=item['requester'].name)
        else:
            # 備用機制
            title_text = self._get_fallback_text("now_playing")
            uploader_text = self._get_fallback_text("uploader")
            duration_text = self._get_fallback_text("duration")
            views_text = self._get_fallback_text("views")
            progress_text = self._get_fallback_text("progress")
            queue_text = self._get_fallback_text("queue")
            queue_empty_text = self._get_fallback_text("queue_empty")
            added_by_text = self._get_fallback_text("added_by", user=item['requester'].name)
        
        embed = discord.Embed(
            title=title_text,
            description=f"**[{item['title']}]({item['url']})**",
            color=discord.Color.blue()
        )
        
        # Add duration field
        minutes, seconds = divmod(item['duration'], 60)
        embed.add_field(name=uploader_text, value=item['author'], inline=True)
        embed.add_field(name=duration_text, value=f"{int(minutes):02d}:{int(seconds):02d}", inline=True)
        
        # Add views field
        try:
            views = int(float(item.get('views', 0)))
            views_str = f"{views:,}"
        except (ValueError, TypeError):
            views_str = "N/A"
        embed.add_field(name=views_text, value=views_str, inline=True)
        
        # Add progress bar
        progress_bar = ProgressDisplay.create_progress_bar(0, item['duration'])
        embed.add_field(name=progress_text, value=progress_bar, inline=False)
        embed.add_field(name=queue_text, value=queue_empty_text, inline=False)
        
        # Add thumbnail
        thumbnail = youtube_manager.get_thumbnail_url(item['video_id'])
        embed.set_thumbnail(url=thumbnail)
        
        # Add footer
        embed.set_footer(text=added_by_text, icon_url=item['user_avatar'])
        
        return embed
        
            
    async def cleanup_view(self, guild_id: int):
        """Clean up the view for a specific guild."""
        if guild_id in self.views:
            view = self.views.pop(guild_id)
            view.stop_progress_updater()
