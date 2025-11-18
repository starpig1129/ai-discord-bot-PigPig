import discord
from typing import Optional
from cogs.language_manager import LanguageManager
from addons.logging import get_logger

log = get_logger(source=__name__, server_id="system")

class SongSelectView(discord.ui.View):
    def __init__(self, player, results, interaction):
        super().__init__(timeout=60)
        self.player = player
        self.results = results
        self.original_interaction = interaction
        self.lang_manager: Optional[LanguageManager] = None
        
        # Add select menu for songs
        self.add_item(SongSelectMenu(self.results, self))
        
    def _get_lang_manager(self):
        """Get language manager instance"""
        if not self.lang_manager and hasattr(self.player, 'bot') and self.player.bot:
            self.lang_manager = self.player.bot.get_cog("LanguageManager")
        return self.lang_manager
        
    def _translate_music(self, *path, **kwargs) -> str:
        """音樂模組專用翻譯方法"""
        lang_manager = self._get_lang_manager()
        if not lang_manager:
            return self._get_fallback_text(path[-1], **kwargs)
        
        guild_id = str(self.original_interaction.guild.id) if self.original_interaction.guild else "0"
        return lang_manager.translate(guild_id, "system", "music", *path, **kwargs)
        
    def _get_fallback_text(self, key: str, **kwargs) -> str:
        """備用文字機制"""
        fallback_texts = {
            "timeout": "⌛ | 選擇歌曲時間已過期",
            "duration_label": "時長: {duration}",
            "placeholder": "選擇要播放的歌曲",
            "queue_full": "❌ | 播放清單已滿",
            "wait_message": "請等待當前歌曲播放完畢後再添加新歌曲",
            "processing": "⏳ | 處理中",
            "processing_desc": "正在處理您的選擇，請稍候...",
            "added": "✅ | 已添加到播放清單： {title}",
            "error": "❌ | 選擇歌曲時發生錯誤"
        }
        
        text = fallback_texts.get(key, key)
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
        
    async def on_timeout(self):
        """Handle view timeout"""
        try:
            await self.original_interaction.edit_original_response(view=None)
        except discord.errors.HTTPException as e:
            if e.code == 50027:  # Invalid Webhook Token
                # Try to send a new message in the same channel
                try:
                    channel = self.original_interaction.channel
                    if channel:
                        embed = discord.Embed(
                            title=self._translate_music("select", "timeout"),
                            color=discord.Color.red()
                        )
                        await channel.send(embed=embed)
                except Exception as inner_e:
                    log.error(f"Failed to send timeout message: {inner_e}")
            else:
                log.error(f"Failed to handle timeout: {e}")
        except Exception as e:
            log.error(f"Unexpected error in timeout handler: {e}")

class SongSelectMenu(discord.ui.Select):
    def __init__(self, results, view):
        self.view_parent = view  # 儲存父 view 以存取翻譯方法
        options = []
        for i, result in enumerate(results, 1):
            # Format duration from seconds to MM:SS
            duration_secs = result.get('duration', 0)
            minutes, seconds = divmod(duration_secs, 60)
            duration_str = f"{int(minutes):02d}:{int(seconds):02d}"
            
            # Get translated duration label
            duration_label = view._translate_music("select", "duration_label", duration=duration_str)
            
            # Create select option with formatted duration
            options.append(discord.SelectOption(
                label=f"{i}. {result['title'][:80]}",  # Truncate long titles
                description=duration_label,
                value=str(i-1)
            ))
            
        placeholder_text = view._translate_music("select", "placeholder")
        super().__init__(
            placeholder=placeholder_text,
            min_values=1,
            max_values=1,
            options=options
        )
        self.results = results

    async def callback(self, interaction: discord.Interaction):
        """Handle song selection"""
        try:
            selected_index = int(self.values[0])
            selected_song = self.results[selected_index].copy()  # Create a copy to avoid modifying original
            
            # Ensure all required fields are present
            selected_song.update({
                'requester': interaction.user,
                'user_avatar': interaction.user.display_avatar.url,
                'title': selected_song.get('title', '未知標題'),
                'duration': selected_song.get('duration', 0),
                'video_id': selected_song.get('video_id', selected_song.get('id', '未知ID')),
                'author': selected_song.get('author', selected_song.get('channel', '未知上傳者')),
                'views': selected_song.get('views', '0'),
                'file_path': None  # Will be set during download
            })
            
            # Get the view instance that contains this select menu
            view = self.view
            if not view:
                log.error("Song selection view not found")
                raise ValueError("View not found")
                
            # Acknowledge the interaction first
            await interaction.response.defer()
            
            # Disable the select menu and update the original message
            self.disabled = True
            processing_embed = discord.Embed(
                title=self.view_parent._translate_music("select", "processing"),
                description=self.view_parent._translate_music("select", "processing_desc"),
                color=discord.Color.blue()
            )
            await view.original_interaction.edit_original_response(embed=processing_embed, view=None)

            # Add song to queue
            guild_id = interaction.guild.id
            queue = view.player.queue_manager.get_queue(guild_id)
            
            if queue.qsize() >= 5:
                embed = discord.Embed(
                    title=self.view_parent._translate_music("select", "queue_full"),
                    description=self.view_parent._translate_music("select", "wait_message"),
                    color=discord.Color.red()
                )
                await view.original_interaction.edit_original_response(embed=embed, view=None)
                return
                
            _, folder = view.player._get_guild_folder(guild_id)
            should_download = queue.qsize() == 0
            
            if should_download:
                video_info, error = await view.player.youtube.download_audio(
                    selected_song['url'],
                    folder,
                    interaction
                )
            else:
                video_info, error = await view.player.youtube.get_video_info_without_download(
                    selected_song['url'],
                    interaction
                )
                
            if error:
                embed = discord.Embed(title=f"❌ | {error}", color=discord.Color.red())
                await view.original_interaction.edit_original_response(embed=embed, view=None)
                return
                
            video_info['added_by'] = interaction.user.id
            await view.player.queue_manager.add_to_front_of_queue(guild_id, video_info)
            
            success_message = self.view_parent._translate_music("select", "added", title=video_info['title'])
            embed = discord.Embed(title=success_message, color=discord.Color.blue())
            await view.original_interaction.edit_original_response(embed=embed, view=None)
            
            # Start playing if not already playing
            voice_client = interaction.guild.voice_client
            if voice_client and not voice_client.is_playing():
                await view.player.play_next(interaction)
                
        except Exception as e:
            log.error(f"Song selection error: {e}")
            try:
                error_message = self.view_parent._translate_music("select", "error")
                error_embed = discord.Embed(title=error_message, color=discord.Color.red())
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=error_embed)
                else:
                    await interaction.followup.send(embed=error_embed)
            except Exception as send_error:
                log.error(f"Failed to send error message: {send_error}")
