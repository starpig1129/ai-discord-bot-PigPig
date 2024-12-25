import discord
import logging as logger

class SongSelectView(discord.ui.View):
    def __init__(self, cog, results, original_interaction):
        super().__init__(timeout=60)
        self.cog = cog
        self.results = results
        self.original_interaction = original_interaction
        
        # 創建選擇菜單
        options = []
        for i, result in enumerate(results, 1):
            options.append(discord.SelectOption(
                label=f"{i}. {result['title'][:80]}", # Discord限制選項標籤最多100字符
                description=f"{result['channel']} | {result.get('duration', 'N/A')}",
                value=str(i-1)
            ))
            
        select = discord.ui.Select(
            placeholder="選擇要播放的歌曲...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        try:
            # 獲取選擇的歌曲
            selected_index = int(interaction.data['values'][0])
            selected_result = self.results[selected_index]
            video_url = f"https://www.youtube.com{selected_result['url_suffix']}"
            
            # 先回應互動
            await interaction.response.defer()
            
            # 添加到播放佇列
            is_valid = await self.cog.add_to_queue(interaction, video_url, is_deferred=True)
            if is_valid:
                # 如果佇列是空的且沒有正在播放，開始播放
                voice_client = interaction.guild.voice_client
                if voice_client and not voice_client.is_playing():
                    await self.cog.play_next(self.original_interaction)
            
            # 禁用選擇菜單
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
        except Exception as e:
            logger.error(f"選擇歌曲時出錯: {e}")
            await interaction.response.send_message("❌ 選擇歌曲時出錯", ephemeral=True)
