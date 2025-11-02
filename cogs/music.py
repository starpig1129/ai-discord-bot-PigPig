import asyncio
import os
import discord
from discord.ext import commands
from discord import app_commands
import logging as logger
import re
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import wavelink
from addons.settings import Settings
from .music_lib.state_manager import StateManager
from .music_lib.ui_manager import UIManager
from .music_lib.custom_queue import CustomQueue
from .music_lib.ui.song_select import SongSelectView
from cogs.language_manager import LanguageManager # Import LanguageManager
from function import func

class PlayMode(wavelink.QueueMode):
    pass

class YTMusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings = Settings()
        self.state_manager = bot.state_manager
        self.ui_manager = bot.ui_manager
        self.lang_manager: Optional[LanguageManager] = None
        self.disconnect_timers = {}

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        logger.info(f"Wavelink node '{payload.node.identifier}' is ready.")


    @app_commands.command(name="mode", description="設置播放模式 (不循環/清單循環/單曲循環)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="不循環", value="no_loop"),
        app_commands.Choice(name="清單循環", value="loop_queue"),
        app_commands.Choice(name="單曲循環", value="loop_single")
    ])
    async def mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        """播放模式命令"""
        guild_id = interaction.guild.id
        if not self.lang_manager: # Ensure lang_manager is loaded
             self.lang_manager = self.bot.get_cog("LanguageManager")
             if not self.lang_manager:
                 await interaction.response.send_message("Language manager not loaded.", ephemeral=True)
                 return
 
         # Localize choices (name is already localized by decorator, but value needs translation for response)
        mode_value = mode.value
        mode_name = self.lang_manager.translate(str(guild_id), "commands", "mode", "choices", mode_value)

        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return

        if mode_value == "no_loop":
            player.queue.mode = wavelink.QueueMode.normal
        elif mode_value == "loop_queue":
            player.queue.mode = wavelink.QueueMode.loop_all
        elif mode_value == "loop_single":
            player.queue.mode = wavelink.QueueMode.loop

        title = self.lang_manager.translate(str(guild_id), "commands", "mode", "responses", "success", mode=mode_name)
        embed = discord.Embed(title=f"✅ | {title}", color=discord.Color.blue())
        message = await interaction.response.send_message(embed=embed)
        state = self.state_manager.get_state(interaction.guild.id)
        state.ui_messages.append(message)

    @app_commands.command(name="shuffle", description="切換隨機播放")
    async def shuffle(self, interaction: discord.Interaction):
        """隨機播放命令"""
        guild_id = interaction.guild.id
        if not self.lang_manager: # Ensure lang_manager is loaded
             self.lang_manager = self.bot.get_cog("LanguageManager")
             if not self.lang_manager:
                 await interaction.response.send_message("Language manager not loaded.", ephemeral=True)
                 return
 
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return

        player.queue.shuffle_mode = not player.queue.shuffle_mode
        status_key = "enabled" if player.queue.shuffle_mode else "disabled"
        status = self.lang_manager.translate(str(guild_id), "commands", "shuffle", "responses", status_key)
        title = self.lang_manager.translate(str(guild_id), "commands", "shuffle", "responses", "success", status=status)
        embed = discord.Embed(title=f"✅ | {title}", color=discord.Color.blue())
        message = await interaction.response.send_message(embed=embed)
        state = self.state_manager.get_state(interaction.guild.id)
        state.ui_messages.append(message)


    @app_commands.command(name="play", description="播放影片(網址或關鍵字) 或 刷新UI")
    async def play(self, interaction: discord.Interaction, query: Optional[str] = None):
        """Play a song from a query or URL, or refresh the UI."""
        player: wavelink.Player
        if not interaction.guild.voice_client:
            queue = functools.partial(CustomQueue, self.bot)
            player = await interaction.user.voice.channel.connect(cls=wavelink.Player, queue_cls=queue)
        else:
            player = interaction.guild.voice_client

        if not query:
            if player.current:
                await self.ui_manager.update_player_ui(interaction, player.current, None, self)
            else:
                await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        tracks: wavelink.Search = await wavelink.YouTubeTrack.search(query)
        if not tracks:
            await interaction.followup.send(f"No tracks found for query: `{query}`", ephemeral=True)
            return

        if isinstance(tracks, wavelink.Playlist):
            for track in tracks.tracks:
                track.extras = {"requester": interaction.user}
            
            # Add first 5 songs to queue, rest to background playlist
            initial_tracks = tracks.tracks[:5]
            background_tracks = tracks.tracks[5:]
            
            added_to_queue = await player.queue.put_wait(initial_tracks)
            
            if not hasattr(player, 'background_playlist'):
                player.background_playlist = []
            player.background_playlist.extend(background_tracks)
            
            await interaction.followup.send(f"Added {added_to_queue} tracks from playlist `{tracks.name}` to the queue. {len(background_tracks)} more are in the background.", ephemeral=True)
        elif len(tracks) > 1:
            view = SongSelectView(self, tracks, interaction)
            await interaction.followup.send("Please select a song:", view=view, ephemeral=True)
        else:
            track = tracks[0]
            track.extras = {"requester": interaction.user}
            await player.queue.put_wait(track)
            await interaction.followup.send(f"Added `{track.title}` to the queue.", ephemeral=True)

        if not player.playing:
            await player.play(player.queue.get(), add_history=True)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        """Handle track ends and play the next song."""
        player = payload.player
        if not player:
            return

        # Decrement the view count for the track that just ended.
        if payload.track and payload.track.extras.view:
            payload.track.extras.view.message and await payload.track.extras.view.message.delete()

        if player.queue.mode is wavelink.QueueMode.loop:
            await player.play(payload.track, add_history=True)
            return

        if player.queue.mode is wavelink.QueueMode.loop_all:
             await player.queue.put_wait(payload.track)

        if hasattr(player, 'background_playlist') and player.background_playlist and player.queue.count < 5:
            needed = 5 - player.queue.count
            tracks_to_add = player.background_playlist[:needed]
            player.background_playlist = player.background_playlist[needed:]
            await player.queue.put_wait(tracks_to_add)

        state = self.state_manager.get_state(player.guild.id)
        if player.queue.is_empty and state.autoplay:
            await self._fill_autoplay_queue(player)
            return

        if not player.queue.is_empty:
             next_track = player.queue.get()
             await player.play(next_track, add_history=True)

    # --- Callback Getters ---
    def get_voice_client(self, guild_id: int) -> Optional[wavelink.Player]:
        guild = self.bot.get_guild(guild_id)
        return guild.voice_client if guild else None

    def get_lang_manager(self) -> Optional[LanguageManager]:
        return self.lang_manager

    # --- Callback Handlers ---
    async def handle_previous(self, interaction: discord.Interaction):
        player = self.get_voice_client(interaction.guild.id)
        if not player:
            await interaction.response.send_message(self.lang_manager.translate(str(interaction.guild.id), "system", "music", "controls", "no_music"), ephemeral=True)
            return

        if not player.queue.history:
            await interaction.response.send_message("No previous songs in history.", ephemeral=True)
            return

        await player.queue.put_history_wait(1)
        await player.stop()

    async def handle_toggle_playback(self, interaction: discord.Interaction):
        player = self.get_voice_client(interaction.guild.id)
        if not player:
            return

        await player.pause(not player.paused)
        await self.ui_manager.update_player_ui(interaction, player.current, None, self)

    async def handle_skip(self, interaction: discord.Interaction):
        player = self.get_voice_client(interaction.guild.id)
        if not player:
            await interaction.response.send_message(self.lang_manager.translate(str(interaction.guild.id), "system", "music", "controls", "no_music"), ephemeral=True)
            return
        
        await player.stop()

    async def handle_stop(self, interaction: discord.Interaction):
        player = self.get_voice_client(interaction.guild.id)
        if not player:
            await interaction.response.send_message(self.lang_manager.translate(str(interaction.guild.id), "system", "music", "controls", "no_music"), ephemeral=True)
            return

        await player.disconnect()

    async def handle_toggle_mode(self, interaction: discord.Interaction):
        player = self.get_voice_client(interaction.guild.id)
        if not player:
            return

        if player.queue.mode == wavelink.QueueMode.normal:
            player.queue.mode = wavelink.QueueMode.loop
        elif player.queue.mode == wavelink.QueueMode.loop:
            player.queue.mode = wavelink.QueueMode.loop_all
        else:
            player.queue.mode = wavelink.QueueMode.normal
        await self.ui_manager.update_player_ui(interaction, player.current, None, self)

    async def handle_toggle_shuffle(self, interaction: discord.Interaction):
        player = self.get_voice_client(interaction.guild.id)
        if not player:
            return

        player.queue.shuffle_mode = not player.queue.shuffle_mode
        await self.ui_manager.update_player_ui(interaction, player.current, None, self)

    async def handle_show_queue(self, interaction: discord.Interaction):
        player = self.get_voice_client(interaction.guild.id)
        if not player or player.queue.is_empty:
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return

        queue_text = "\n".join([f"{i+1}. {track.title}" for i, track in enumerate(player.queue)])
        embed = discord.Embed(title="Queue", description=queue_text)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def handle_toggle_autoplay(self, interaction: discord.Interaction):
        """Toggle autoplay mode."""
        guild_id = interaction.guild.id
        state = self.state_manager.get_state(guild_id)
        state.autoplay = not state.autoplay
        self.state_manager.update_state(guild_id, autoplay=state.autoplay)
        logger.info(f"[Music] Guild ID: {interaction.guild.id}, Autoplay status toggled to: {state.autoplay}")

        status_key = "enabled" if state.autoplay else "disabled"
        status_str = self.lang_manager.translate(str(guild_id), "system", "music", "autoplay", status_key)
        title = self.lang_manager.translate(str(guild_id), "system", "music", "autoplay", "toggled", status=status_str)
        await interaction.response.send_message(f"✅ | {title}", ephemeral=True, delete_after=5)

    async def get_queue_text(self, guild_id: int) -> str:
        """Generates the text for the queue display."""
        player = self.get_voice_client(guild_id)
        if not player:
            return self.lang_manager.translate(str(guild_id), "system", "music", "player", "queue_empty")

        text = ""
        if player.current:
            prefix = self.lang_manager.translate(str(guild_id), "system", "music", "controls", "now_playing_prefix")
            text += f"{prefix} {player.current.title}\n\n"
        
        if not player.queue.is_empty:
            label = self.lang_manager.translate(str(guild_id), "system", "music", "controls", "queue_songs")
            text += f"{label}\n"
            for i, track in enumerate(player.queue, 1):
                text += f"{i}. {track.title}\n"
        
        return text if text.strip() else self.lang_manager.translate(str(guild_id), "system", "music", "player", "queue_empty")

    async def _fill_autoplay_queue(self, player: wavelink.Player):
        """Fills the queue with recommended songs when autoplay is on."""
        if not player or not player.current:
            return

        related_tracks = await self.get_related_videos(player.current)
        if not related_tracks:
            return

        for track in related_tracks:
            track.extras = {"requester": self.bot.user}
            await player.queue.put_wait(track)

    async def get_related_videos(self, track: wavelink.Track, limit: int = 5, exclude_ids: set = None):
        """Gets related videos from YouTube using a multi-strategy approach."""
        if not track:
            return []
        
        if exclude_ids is None:
            exclude_ids = set()
        exclude_ids.add(track.identifier)

        final_results = []

        # Strategy 1: Search by author
        if track.author:
            try:
                author_results = await wavelink.YouTubeTrack.search(track.author)
                processed = [t for t in author_results if t.identifier not in exclude_ids]
                final_results.extend(processed[:limit])
            except Exception as e:
                logger.error(f"Autoplay (author search) failed: {e}")

        # Strategy 2: Search by cleaned title
        if len(final_results) < limit:
            try:
                clean_title = re.sub(r'\s*\(.*?(official|video|lyric|mv|audio|4k|hd).*?\)\s*|\[.*?\]', '', track.title, flags=re.IGNORECASE).strip()
                if clean_title:
                    title_results = await wavelink.YouTubeTrack.search(clean_title)
                    processed = [t for t in title_results if t.identifier not in exclude_ids and t.identifier not in {r.identifier for r in final_results}]
                    final_results.extend(processed[:limit - len(final_results)])
            except Exception as e:
                logger.error(f"Autoplay (title search) failed: {e}")

        return final_results

    async def _cleanup_voice_session(self, guild_id: int):
        """Cleans up the voice session for a guild."""
        player = self.get_voice_client(guild_id)
        if player:
            await player.disconnect()

        await self.ui_manager.cleanup_view(guild_id)
        state = self.state_manager.get_state(guild_id)
        for old_message in state.ui_messages:
            try:
                await old_message.delete()
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
        state.ui_messages.clear()

    async def _cancel_disconnect_timer(self, guild_id: int):
        """Cancels the disconnect timer for a guild."""
        if guild_id in self.disconnect_timers:
            self.disconnect_timers[guild_id].cancel()
            del self.disconnect_timers[guild_id]
            logger.info(f"[Music] Guild ID: {guild_id}, Cancelled disconnect timer.")

    async def _start_disconnect_timer(self, guild_id: int):
        """Starts the disconnect timer for a guild."""
        await self._cancel_disconnect_timer(guild_id)
        logger.info(f"[Music] Guild ID: {guild_id}, Player paused, starting 5-minute disconnect timer.")
        self.disconnect_timers[guild_id] = self.bot.loop.create_task(
            self._disconnect_after_delay(guild_id)
        )

    async def _disconnect_after_delay(self, guild_id: int):
        """Disconnects the bot after a 5-minute delay if it's still paused."""
        await asyncio.sleep(300)
        player = self.get_voice_client(guild_id)
        if player and player.paused:
            logger.info(f"[Music] Guild ID: {guild_id}, Idle for 5 minutes, disconnecting.")
            await self._cleanup_voice_session(guild_id)

        if guild_id in self.disconnect_timers:
            del self.disconnect_timers[guild_id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state changes, including auto-pause and auto-disconnect."""
        if member.id == self.bot.user.id and before.channel and not after.channel:
            player = self.get_voice_client(member.guild.id)
            if player:
                await self._cleanup_voice_session(member.guild.id)
            return

        player = self.get_voice_client(member.guild.id)
        if not player or not player.channel:
            return

        if before.channel == player.channel or after.channel == player.channel:
            human_members = [m for m in player.channel.members if not m.bot]
            if not human_members and player.playing:
                await player.pause(True)
                await self._start_disconnect_timer(member.guild.id)
            elif human_members and player.paused:
                await player.pause(False)
                await self._cancel_disconnect_timer(member.guild.id)

async def setup(bot):
    """Initialize the music cog"""
    cog = YTMusic(bot)
    await cog.setup_hook()  # Initialize async components
    await bot.add_cog(cog)
