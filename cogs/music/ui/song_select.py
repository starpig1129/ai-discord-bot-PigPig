import discord
import logging as logger

class SongSelectView(discord.ui.View):
    def __init__(self, player, results, interaction):
        super().__init__(timeout=60)
        self.player = player
        self.results = results
        self.original_interaction = interaction
        
        # Add select menu for songs
        self.add_item(SongSelectMenu(self.results))
        
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
                            title="⌛ | 選擇歌曲時間已過期",
                            color=discord.Color.red()
                        )
                        await channel.send(embed=embed)
                except Exception as inner_e:
                    logger.error(f"Failed to send timeout message: {inner_e}")
            else:
                logger.error(f"Failed to handle timeout: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in timeout handler: {e}")

class SongSelectMenu(discord.ui.Select):
    def __init__(self, results):
        options = []
        for i, result in enumerate(results[:5], 1):  # Limit to 5 choices
            # Format duration from seconds to MM:SS
            duration_secs = result.get('duration', 0)
            minutes, seconds = divmod(duration_secs, 60)
            duration_str = f"{int(minutes):02d}:{int(seconds):02d}"
            
            # Create select option with formatted duration
            options.append(discord.SelectOption(
                label=f"{i}. {result['title'][:80]}",  # Truncate long titles
                description=f"時長: {duration_str}",
                value=str(i-1)
            ))
            
        super().__init__(
            placeholder="選擇要播放的歌曲",
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
                logger.error("Song selection view not found")
                raise ValueError("View not found")
                
            # Acknowledge the interaction first
            await interaction.response.defer(ephemeral=False)
            
            # Disable the select menu
            self.disabled = True
            try:
                if hasattr(interaction, 'message'):
                    await interaction.message.edit(view=view)
            except Exception as e:
                logger.error(f"Failed to update view: {e}")
                # Continue anyway since this is not critical
            
            # Add song to queue
            guild_id = interaction.guild.id
            queue = view.player.queue_manager.get_queue(guild_id)
            
            if queue.qsize() >= 5:
                embed = discord.Embed(
                    title="❌ | 播放清單已滿",
                    description="請等待當前歌曲播放完畢後再添加新歌曲",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
                
            # Send processing message
            processing_embed = discord.Embed(
                title="⏳ | 處理中",
                description="正在處理您的選擇，請稍候...",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=processing_embed)
                
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
                await interaction.followup.send(embed=embed)
                return
                
            await view.player.queue_manager.add_to_queue(guild_id, video_info)
            try:
                embed = discord.Embed(title=f"✅ | 已添加到播放清單： {video_info['title']}", color=discord.Color.blue())
                await interaction.followup.send(embed=embed)
            except discord.errors.HTTPException as e:
                if e.code == 50027:  # Invalid Webhook Token
                    try:
                        # Try to send directly to channel
                        await interaction.channel.send(embed=embed)
                    except Exception as inner_e:
                        logger.error(f"Failed to send queue addition message: {inner_e}")
                else:
                    raise
            
            # Start playing if not already playing
            voice_client = interaction.guild.voice_client
            if voice_client and not voice_client.is_playing():
                await view.player.play_next(interaction)
                
        except Exception as e:
            logger.error(f"Song selection error: {e}")
            try:
                error_embed = discord.Embed(title="❌ | 選擇歌曲時發生錯誤", color=discord.Color.red())
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=error_embed)
                else:
                    await interaction.followup.send(embed=error_embed)
            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}")
