import discord
import logging as logger
from typing import Optional
from cogs.language_manager import LanguageManager

import discord
import logging as logger
from typing import Optional, List
import wavelink
from cogs.language_manager import LanguageManager

class SongSelectView(discord.ui.View):
    def __init__(self, music_cog, results: List[wavelink.Track], interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.music_cog = music_cog
        self.results = results
        self.original_interaction = interaction
        self.lang_manager: Optional[LanguageManager] = None
        
        self.add_item(SongSelectMenu(self.results, self))
        
    def _get_lang_manager(self):
        if not self.lang_manager:
            self.lang_manager = self.music_cog.bot.get_cog("LanguageManager")
        return self.lang_manager
        
    def _translate_music(self, *path, **kwargs) -> str:
        lang_manager = self._get_lang_manager()
        if not lang_manager:
            return self._get_fallback_text(path[-1], **kwargs)
        
        guild_id = str(self.original_interaction.guild.id) if self.original_interaction.guild else "0"
        return lang_manager.translate(guild_id, "system", "music", *path, **kwargs)
        
    def _get_fallback_text(self, key: str, **kwargs) -> str:
        fallback_texts = {
            "timeout": "⌛ | Selection timed out",
            "duration_label": "Duration: {duration}",
            "placeholder": "Select a song to play",
            "processing": "⏳ | Processing your selection...",
            "added": "✅ | Added to queue: {title}",
            "error": "❌ | An error occurred while selecting the song."
        }
        text = fallback_texts.get(key, key)
        return text.format(**kwargs)
        
    async def on_timeout(self):
        try:
            await self.original_interaction.edit_original_response(view=None)
        except discord.errors.HTTPException as e:
            logger.error(f"Failed to handle timeout: {e}")

class SongSelectMenu(discord.ui.Select):
    def __init__(self, results: List[wavelink.Track], view: SongSelectView):
        self.view_parent = view
        options = []
        for i, track in enumerate(results):
            minutes, seconds = divmod(track.length / 1000, 60)
            duration_str = f"{int(minutes):02d}:{int(seconds):02d}"
            duration_label = view._translate_music("select", "duration_label", duration=duration_str)
            
            options.append(discord.SelectOption(
                label=f"{i + 1}. {track.title[:80]}",
                description=duration_label,
                value=str(i)
            ))
            
        placeholder_text = view._translate_music("select", "placeholder")
        super().__init__(placeholder=placeholder_text, options=options)
        self.results = results

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_index = int(self.values[0])
            track = self.results[selected_index]
            track.extras = {"requester": interaction.user}

            await interaction.response.defer()
            
            self.disabled = True
            processing_embed = discord.Embed(
                title=self.view_parent._translate_music("select", "processing"),
                color=discord.Color.blue()
            )
            await self.view_parent.original_interaction.edit_original_response(embed=processing_embed, view=None)

            player: wavelink.Player = interaction.guild.voice_client
            if not player:
                player = await interaction.user.voice.channel.connect(cls=wavelink.Player)

            await player.queue.put_wait(track)
            
            success_message = self.view_parent._translate_music("select", "added", title=track.title)
            embed = discord.Embed(title=success_message, color=discord.Color.blue())
            await self.view_parent.original_interaction.edit_original_response(embed=embed, view=None)
            
            if not player.playing:
                await player.play(player.queue.get(), add_history=True)
                
        except Exception as e:
            logger.error(f"Song selection error: {e}")
            error_message = self.view_parent._translate_music("select", "error")
            await interaction.followup.send(error_message, ephemeral=True)
