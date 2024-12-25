import discord

class ProgressSelect(discord.ui.Select):
    def __init__(self, duration, cog):
        self.duration = duration
        self.cog = cog
        
        # 創建進度選項（10個刻度）
        options = []
        for i in range(11):
            position = int(duration * i / 10)
            minutes, seconds = divmod(position, 60)
            options.append(
                discord.SelectOption(
                    label=f"{minutes:02d}:{seconds:02d}",
                    value=str(position),
                    description=f"跳轉至 {i*10}% 處"
                )
            )
            
        super().__init__(
            placeholder="拖曳調整進度...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        position = int(self.values[0])
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await self.cog.play_from_position(interaction, position)
            
            # Get the view from the message
            view = interaction.message.view
            if view:
                # 更新進度條位置
                view.current_position = position
                
                # 重新啟動進度更新任務
                if view.update_task:
                    view.update_task.cancel()
                view.update_task = self.cog.bot.loop.create_task(
                    view.update_progress(self.duration)
                )
            
            await interaction.response.defer()
