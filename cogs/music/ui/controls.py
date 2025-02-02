import discord
import asyncio
import logging as logger
from .progress import ProgressDisplay

class MusicControlView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, player):
        super().__init__(timeout=None)
        self.guild = interaction.guild
        self.player = player
        self.current_position = 0
        self.message = None
        self.update_task = None
        self.current_embed = None
        
        # Initialize button states without updating message
        asyncio.create_task(self.update_button_state(update_message=False))

    async def update_button_state(self, update_message: bool = True):
        """Update button states based on current playback and mode status"""
        voice_client = self.guild.voice_client
        guild_id = self.guild.id
        
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
                    current_mode = self.player.queue_manager.get_play_mode(guild_id).value
                    child.emoji = discord.PartialEmoji.from_str(mode_emojis[current_mode])
                
                # Shuffle button
                elif child.custom_id == "toggle_shuffle":
                    is_shuffle = self.player.queue_manager.get_queue_state(guild_id).shuffle_enabled
                    child.style = discord.ButtonStyle.green if is_shuffle else discord.ButtonStyle.gray
                    child.emoji = discord.PartialEmoji.from_str('🔀')
        
        # Only update message if requested and message exists
        if update_message and self.message:
            try:
                await self.message.edit(view=self)
            except Exception as e:
                logger.error(f"Failed to update button state: {e}")

    async def update_progress(self, duration):
        try:
            if hasattr(self, '_is_updating') and self._is_updating:
                return
                
            self._is_updating = True
            # Update button state when starting progress tracking
            await self.update_button_state()
            update_interval = 5  # Update every 5 seconds
            last_update = 0
            message_refresh_interval = 600  # Refresh message every 10 minutes
            last_message_refresh = asyncio.get_event_loop().time()
            
            try:
                while True:
                    if not self.guild.voice_client or not self.guild.voice_client.is_playing():
                        await self.update_button_state()  # Update button state when playback stops
                        break
                        
                    self.current_position += 1
                    if self.current_position > duration:
                        await self.update_button_state()  # Update button state when song ends
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
        voice_client = self.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)
            return

        state = self.player.state_manager.get_state(self.guild.id)
        queue = self.player.queue_manager.get_queue(self.guild.id)
        if not queue:
            await interaction.response.send_message("❌ 沒有可播放的歌曲！", ephemeral=True)
            return

        # Copy queue items
        queue_items = []
        temp_queue = asyncio.Queue()
        while not queue.empty():
            item = await queue.get()
            queue_items.append(item)

        # Reorganize queue
        new_queue = asyncio.Queue()
        if state.current_song:
            await new_queue.put(state.current_song)
        for item in queue_items:
            await new_queue.put(item)

        # Cancel update task
        if self.update_task:
            self.update_task.cancel()
            self.update_task = None
            self._is_updating = False
            
        # Update queue and stop current playback
        self.player.queue_manager.get_queue_state(self.guild.id).queue = new_queue
        
        # 在停止播放前先更新按鈕狀態
        await self.update_button_state()
        voice_client.stop()
        
        # 等待一小段時間確保狀態已更新
        await asyncio.sleep(0.5)
        
        # 再次更新按鈕狀態以確保顯示正確
        await self.update_button_state()
        await self.update_embed(interaction, f"⏮️ {interaction.user.name} 返回上一首")
        await interaction.response.defer()

    @discord.ui.button(emoji='⏯️', style=discord.ButtonStyle.gray, custom_id="toggle_playback")
    async def toggle_playback(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if voice_client:
            if voice_client.is_playing():
                # 在暫停前先更新按鈕狀態
                await self.update_button_state()
                voice_client.pause()
                # 等待一小段時間確保狀態已更新
                await asyncio.sleep(0.1)
                await self.update_button_state()
                await self.update_embed(interaction, f"⏸️ {interaction.user.name} 暫停了音樂")
                if self.update_task:
                    self.update_task.cancel()
                    self.update_task = None
                    self._is_updating = False
            elif voice_client.is_paused():
                # 在繼續播放前先更新按鈕狀態
                await self.update_button_state()
                voice_client.resume()
                # 等待一小段時間確保狀態已更新
                await asyncio.sleep(0.1)
                await self.update_button_state()
                await self.update_embed(interaction, f"▶️ {interaction.user.name} 繼續了音樂")
                if self.update_task:
                    self.update_task.cancel()
                    self.update_task = None
                    self._is_updating = False
                state = self.player.state_manager.get_state(self.guild.id)
                if state.current_song:
                    self.update_task = asyncio.create_task(
                        self.update_progress(state.current_song["duration"])
                    )
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.gray, custom_id="skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)
            return

        queue = self.player.queue_manager.get_queue(self.guild.id)
        if not queue or queue.empty():
            if self.player.queue_manager.has_playlist_songs(self.guild.id):
                _, folder = self.player._get_guild_folder(self.guild.id)
                next_songs = await self.player.queue_manager.get_next_playlist_songs(
                    self.guild.id,
                    count=1
                )
                if next_songs:
                    await self.player.queue_manager.add_to_queue(self.guild.id, next_songs[0])

        if self.update_task:
            self.update_task.cancel()
            self.update_task = None
            self._is_updating = False
            
        # 在停止播放前先更新按鈕狀態
        await self.update_button_state()
        voice_client.stop()
        
        # 等待一小段時間確保狀態已更新
        await asyncio.sleep(0.5)
        
        # 再次更新按鈕狀態以確保顯示正確
        await self.update_button_state()
        await self.update_embed(interaction, f"⏭️ {interaction.user.name} 跳過了音樂")
        await interaction.response.defer()

    @discord.ui.button(emoji='⏹️', style=discord.ButtonStyle.red, custom_id="stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if voice_client:
            queue = self.player.queue_manager.get_queue(self.guild.id)
            if queue:
                while not queue.empty():
                    await queue.get()
                    
            if self.update_task:
                self.update_task.cancel()
                self.update_task = None
                self._is_updating = False
            
            # 在停止播放前先更新按鈕狀態
            await self.update_button_state()
            voice_client.stop()
            
            # 等待一小段時間確保狀態已更新
            await asyncio.sleep(0.1)
            
            await voice_client.disconnect()
            
            # 再次更新按鈕狀態以確保顯示正確
            await self.update_button_state()
            await self.update_embed(interaction, f"⏹️ {interaction.user.name} 停止了播放", discord.Color.red())
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='🔄', style=discord.ButtonStyle.gray, custom_id="toggle_mode")
    async def toggle_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換播放模式"""
        guild_id = self.guild.id
        current_mode = self.player.queue_manager.get_play_mode(guild_id)
        
        mode_order = ["no_loop", "loop_queue", "loop_single"]
        current_index = mode_order.index(current_mode.value)
        next_mode = mode_order[(current_index + 1) % len(mode_order)]
        
        self.player.queue_manager.set_play_mode(guild_id, next_mode)
        
        mode_emojis = {
            "no_loop": '➡️',
            "loop_queue": '🔁',
            "loop_single": '🔂'
        }
        
        mode_names = {
            "no_loop": "不循環",
            "loop_queue": "清單循環",
            "loop_single": "單曲循環"
        }

        await self.update_button_state()
        await self.update_embed(interaction, f"🔄 {interaction.user.name} 將播放模式設為 {mode_names[next_mode]}")
        await interaction.response.defer()

    @discord.ui.button(emoji='🔀', style=discord.ButtonStyle.gray, custom_id="toggle_shuffle")
    async def toggle_shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換隨機播放"""
        guild_id = self.guild.id
        is_shuffle = self.player.queue_manager.toggle_shuffle(guild_id)
        
        status = "開啟" if is_shuffle else "關閉"
        await self.update_button_state()
        await self.update_embed(interaction, f"🔀 {interaction.user.name} {status}隨機播放")
        await interaction.response.defer()

    @discord.ui.button(emoji='📜', style=discord.ButtonStyle.gray, custom_id="show_queue")
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = self.guild.id
        queue = self.player.queue_manager.get_queue(guild_id)
        state = self.player.state_manager.get_state(guild_id)
        
        queue_items = []
        if queue:
            temp_queue = asyncio.Queue()
            while not queue.empty():
                item = await queue.get()
                queue_items.append(item)
                await temp_queue.put(item)
            self.player.queue_manager.get_queue_state(guild_id).queue = temp_queue

        if self.current_embed and self.message:
            queue_text = ""
            
            if state.current_song:
                minutes, seconds = divmod(float(state.current_song["duration"]), 60)
                queue_text += f"▶️ 正在播放: {state.current_song['title']} | {int(minutes):02d}:{int(seconds):02d}\n\n"
            
            if queue_items:
                queue_text += "待播放歌曲:\n"
                for i, item in enumerate(queue_items, 1):
                    minutes, seconds = divmod(float(item["duration"]), 60)
                    queue_text += f"{i}. {item['title']} | {int(minutes):02d}:{int(seconds):02d}\n"
            
            if not queue_text:
                queue_text = "清單為空"
            
            self.current_embed.set_field_at(4, name="📜 播放清單", value=queue_text, inline=False)
            # Use the common update_embed method which handles message recreation
            await self.update_embed(interaction, self.current_embed.title, self.current_embed.color)
            await interaction.response.defer()
        else:
            await interaction.response.send_message("無法更新播放清單", ephemeral=True)
