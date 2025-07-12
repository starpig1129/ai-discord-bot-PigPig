import asyncio
import discord
import logging as logger
from typing import Optional, Dict, Any
from .ui.controls import MusicControlView
from .ui.progress import ProgressDisplay
from cogs.language_manager import LanguageManager

class UIManager:
    def __init__(self, bot=None):
        self._current_view = None
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
        
    async def update_player_ui(self, interaction: discord.Interaction, item: Dict[str, Any],
                             current_message: Optional[discord.Message], youtube_manager, player=None) -> discord.Message:
        """Update or create the music player UI"""
        try:
            guild_id = str(interaction.guild.id) if interaction.guild else None
            embed = self._create_player_embed(item, youtube_manager, guild_id)
            view = MusicControlView(interaction, player)  # Pass the player instance
            
            # Get player state to track messages
            state = player.state_manager.get_state(interaction.guild.id)
            
            # Clean up all old UI messages first
            for old_message in state.ui_messages:
                try:
                    await old_message.delete()
                except:
                    pass  # Ignore cleanup failures
            state.ui_messages.clear()
            
            # First try to use the existing message if available
            if current_message:
                try:
                    await current_message.edit(embed=embed, view=view)
                    message = current_message
                    # Add current message to tracking if successful
                    state.ui_messages.append(message)
                except (discord.errors.HTTPException, discord.errors.NotFound, discord.errors.Forbidden):
                    current_message = None  # Mark as unavailable for retry
            
            # If no current message or edit failed, try to send a new message
            if not current_message:
                
                # Try multiple methods to send the message
                message = None
                errors = []
                
                # Method 1: Try interaction followup
                if not message:
                    try:
                        message = await interaction.followup.send(embed=embed, view=view)
                    except Exception as e:
                        errors.append(f"Followup failed: {str(e)}")
                
                # Method 2: Try interaction channel
                if not message and interaction.channel:
                    try:
                        message = await interaction.channel.send(embed=embed, view=view)
                    except Exception as e:
                        errors.append(f"Channel send failed: {str(e)}")
                
                # If all methods failed, log errors and raise the last exception
                if not message:
                    error_msg = "All UI update methods failed:\n" + "\n".join(errors)
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
                
                # Add new message to tracking list
                state.ui_messages.append(message)
            
            # Setup view properties
            view.message = message
            view.current_embed = embed
            view.current_position = 0
            
            # Update button states now that message is set
            await view.update_button_state()
            
            # Handle update task
            if self._current_view and self._current_view.update_task:
                await self._cancel_update_task()
            
            self._current_view = view
            view.update_task = asyncio.create_task(view.update_progress(item['duration']))
            
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
        
            
    async def _cancel_update_task(self):
        """Cancel the current update task"""
        self._current_view.update_task.cancel()
        try:
            await asyncio.wait_for(self._current_view.update_task, timeout=0.1)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
