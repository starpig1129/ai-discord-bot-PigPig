import discord
import asyncio
import logging as logger
from .progress import ProgressSelect
from ..queue import (
    guild_queues,
    PlayMode,
    get_play_mode,
    set_play_mode,
    is_shuffle_enabled,
    toggle_shuffle
)

class MusicControlView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, cog):
        super().__init__(timeout=None)
        self.guild = interaction.guild
        self.cog = cog
        self.current_position = 0
        self.message = None
        self.update_task = None
        self.current_embed = None

    def create_progress_bar(self, current, total, length=20):
        filled = int(length * current / total)
        bar = "▰" * filled + "▱" * (length - filled)
        minutes_current, seconds_current = divmod(current, 60)
        minutes_total, seconds_total = divmod(total, 60)
        return f"{minutes_current:02d}:{seconds_current:02d} {bar} {minutes_total:02d}:{seconds_total:02d}"

    async def update_progress(self, duration):
        try:
            while True:
                if not self.guild.voice_client or not self.guild.voice_client.is_playing():
                    break
                
                self.current_position += 1
                if self.current_position > duration:
                    break
                    
                if self.current_embed and self.message:
                    progress_bar = self.create_progress_bar(self.current_position, duration)
                    self.current_embed.set_field_at(3, name="🎵 播放進度", value=progress_bar, inline=False)
                    await self.message.edit(embed=self.current_embed)
                
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Progress update error: {e}")

    async def update_embed(self, interaction: discord.Interaction, title: str, color: discord.Color = discord.Color.blue()):
        if self.current_embed and self.message:
            self.current_embed.title = title
            self.current_embed.color = color
            await self.message.edit(embed=self.current_embed)

    def add_progress_select(self):
        """添加進度條選擇器"""
        if hasattr(self.cog, 'current_song'):
            progress_select = ProgressSelect(self.cog.current_song["duration"], self.cog)
            self.add_item(progress_select)

    @discord.ui.button(emoji='⏮️', style=discord.ButtonStyle.gray)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if voice_client:
            # 重置當前歌曲
            voice_client.stop()
            # 將當前歌曲重新加入隊列前端
            if hasattr(self.cog, 'current_song') and self.cog.current_song:
                queue = guild_queues.get(self.guild.id)
                if queue:
                    new_queue = asyncio.Queue()
                    await new_queue.put(self.cog.current_song)
                    while not queue.empty():
                        item = await queue.get()
                        await new_queue.put(item)
                    guild_queues[self.guild.id] = new_queue
            await self.update_embed(interaction, f"⏮️ {interaction.user.name} 返回上一首")
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='⏯️', style=discord.ButtonStyle.gray)
    async def toggle_playback(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if voice_client:
            if voice_client.is_playing():
                voice_client.pause()
                await self.update_embed(interaction, f"⏸️ {interaction.user.name} 暫停了音樂")
                if self.update_task:
                    self.update_task.cancel()
            elif voice_client.is_paused():
                voice_client.resume()
                await self.update_embed(interaction, f"▶️ {interaction.user.name} 繼續了音樂")
                # 重新啟動進度更新
                if hasattr(self.cog, 'current_song'):
                    self.update_task = self.cog.bot.loop.create_task(
                        self.update_progress(self.cog.current_song["duration"])
                    )
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.gray)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if voice_client:
            voice_client.stop()
            await self.update_embed(interaction, f"⏭️ {interaction.user.name} 跳過了音樂")
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='⏹️', style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = self.guild.voice_client
        if voice_client:
            # 清空播放隊列
            queue = guild_queues.get(self.guild.id)
            if queue:
                while not queue.empty():
                    await queue.get()
            # 停止播放
            voice_client.stop()
            await voice_client.disconnect()
            await self.update_embed(interaction, f"⏹️ {interaction.user.name} 停止了播放", discord.Color.red())
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂！", ephemeral=True)

    @discord.ui.button(emoji='🔄', style=discord.ButtonStyle.gray)
    async def toggle_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換播放模式"""
        guild_id = self.guild.id
        current_mode = get_play_mode(guild_id)
        
        # 循環切換模式
        mode_order = [PlayMode.NO_LOOP, PlayMode.LOOP_QUEUE, PlayMode.LOOP_SINGLE]
        current_index = mode_order.index(current_mode)
        next_mode = mode_order[(current_index + 1) % len(mode_order)]
        
        set_play_mode(guild_id, next_mode)
        
        # 更新按鈕樣式
        mode_emojis = {
            PlayMode.NO_LOOP: '➡️',
            PlayMode.LOOP_QUEUE: '🔁',
            PlayMode.LOOP_SINGLE: '🔂'
        }
        button.emoji = mode_emojis[next_mode]
        
        mode_names = {
            PlayMode.NO_LOOP: "不循環",
            PlayMode.LOOP_QUEUE: "清單循環",
            PlayMode.LOOP_SINGLE: "單曲循環"
        }
        
        await self.update_embed(interaction, f"🔄 {interaction.user.name} 將播放模式設為 {mode_names[next_mode]}")
        await interaction.response.defer()

    @discord.ui.button(emoji='🔀', style=discord.ButtonStyle.gray)
    async def toggle_shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換隨機播放"""
        guild_id = self.guild.id
        is_shuffle = toggle_shuffle(guild_id)
        
        # 更新按鈕樣式
        button.style = discord.ButtonStyle.green if is_shuffle else discord.ButtonStyle.gray
        
        status = "開啟" if is_shuffle else "關閉"
        await self.update_embed(interaction, f"🔀 {interaction.user.name} {status}隨機播放")
        await interaction.response.defer()

    @discord.ui.button(emoji='📜', style=discord.ButtonStyle.gray)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = guild_queues.get(self.guild.id)
        if not queue or queue.empty():
            await interaction.response.send_message("目前沒有歌曲在播放清單中", ephemeral=True)
            return

        # 複製隊列內容而不消耗原隊列
        queue_copy = []
        temp_queue = asyncio.Queue()
        while not queue.empty():
            item = await queue.get()
            queue_copy.append(item)
            await temp_queue.put(item)
        guild_queues[self.guild.id] = temp_queue

        # 更新播放清單到當前 embed
        if self.current_embed and self.message:
            queue_text = ""
            for i, item in enumerate(queue_copy, 1):
                minutes, seconds = divmod(item["duration"], 60)
                queue_text += f"{i}. {item['title']} | {minutes:02d}:{seconds:02d}\n"
            
            self.current_embed.set_field_at(4, name="📜 播放清單", value=queue_text if queue_text else "清單為空", inline=False)
            await self.message.edit(embed=self.current_embed)
            await interaction.response.defer()
        else:
            await interaction.response.send_message("無法更新播放清單", ephemeral=True)
