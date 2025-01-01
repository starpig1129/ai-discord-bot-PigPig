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
        except:
            pass

class SongSelectMenu(discord.ui.Select):
    def __init__(self, results):
        options = []
        for i, result in enumerate(results[:5], 1):  # Limit to 5 choices
            duration = result.get('duration', 'N/A')
            options.append(discord.SelectOption(
                label=f"{i}. {result['title'][:80]}",  # Truncate long titles
                description=f"Duration: {duration}",
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
            selected_song = self.results[selected_index]
            
            # Get the view instance that contains this select menu
            view = self.view
            if not view:
                return
                
            # Disable the select menu to prevent multiple selections
            self.disabled = True
            await interaction.response.edit_message(view=view)
            
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
            embed = discord.Embed(title=f"✅ | 已添加到播放清單： {video_info['title']}", color=discord.Color.blue())
            await interaction.followup.send(embed=embed)
            
            # Start playing if not already playing
            voice_client = interaction.guild.voice_client
            if voice_client and not voice_client.is_playing():
                await view.player.play_next(interaction)
                
        except Exception as e:
            logger.error(f"Song selection error: {e}")
            embed = discord.Embed(title="❌ | 選擇歌曲時發生錯誤", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
