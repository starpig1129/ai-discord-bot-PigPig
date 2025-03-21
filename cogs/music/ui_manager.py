import asyncio
import discord
import logging as logger
from typing import Optional, Dict, Any
from .ui.controls import MusicControlView
from .ui.progress import ProgressDisplay

class UIManager:
    def __init__(self):
        self._current_view = None
        
    async def update_player_ui(self, interaction: discord.Interaction, item: Dict[str, Any], 
                             current_message: Optional[discord.Message], youtube_manager, player=None) -> discord.Message:
        """Update or create the music player UI"""
        try:
            embed = self._create_player_embed(item, youtube_manager)
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
            
    def _create_player_embed(self, item: Dict[str, Any], youtube_manager) -> discord.Embed:
        """Create the player embed with song information"""
        embed = discord.Embed(
            title="🎵 正在播放",
            description=f"**[{item['title']}]({item['url']})**",
            color=discord.Color.blue()
        )
        
        # Add duration field
        minutes, seconds = divmod(item['duration'], 60)
        embed.add_field(name="👤 上傳頻道", value=item['author'], inline=True)
        embed.add_field(name="⏱️ 播放時長", value=f"{int(minutes):02d}:{int(seconds):02d}", inline=True)
        
        # Add views field
        try:
            views = int(float(item.get('views', 0)))
            views_str = f"{views:,}"
        except (ValueError, TypeError):
            views_str = "N/A"
        embed.add_field(name="👀 觀看次數", value=views_str, inline=True)
        
        # Add progress bar
        progress_bar = ProgressDisplay.create_progress_bar(0, item['duration'])
        embed.add_field(name="🎵 播放進度", value=progress_bar, inline=False)
        embed.add_field(name="📜 播放清單", value="清單為空", inline=False)
        
        # Add thumbnail
        thumbnail = youtube_manager.get_thumbnail_url(item['video_id'])
        embed.set_thumbnail(url=thumbnail)
        
        # Add footer
        embed.set_footer(text=f"由 {item['requester'].name} 添加", icon_url=item['user_avatar'])
        
        return embed
        
            
    async def _cancel_update_task(self):
        """Cancel the current update task"""
        self._current_view.update_task.cancel()
        try:
            await asyncio.wait_for(self._current_view.update_task, timeout=0.1)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
