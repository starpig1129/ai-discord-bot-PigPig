import os
import asyncio
from addons.logging import get_logger
log = get_logger(source=__name__, server_id="system")
logger = log
from discord import FFmpegPCMAudio
from typing import Dict, Any

class AudioManager:
    def __init__(self):
        self.current_audio = None
        
    def create_audio_source(self, song: Dict[str, Any]) -> FFmpegPCMAudio:
        """Create an FFmpeg audio source based on song information."""
        is_live = song.get('is_live', False)
        
        if is_live:
            stream_url = song.get('stream_url')
            if not stream_url:
                raise ValueError("Live song is missing stream_url")
            
            # FFmpeg parameters optimized for live streams
            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn'
            }
            return FFmpegPCMAudio(stream_url, **ffmpeg_options)
        else:
            file_path = song.get('file_path')
            if not file_path or not os.path.exists(file_path):
                raise ValueError(f"Audio file does not exist or invalid path: {file_path}")
            
            # Standard parameters for local files
            return FFmpegPCMAudio(file_path)
        
    async def delete_file(self, guild_id: int, file_path: str):
        """Non-blocking file deletion using asyncio.to_thread"""
        try:
            if os.path.exists(file_path):
                await asyncio.to_thread(os.remove, file_path)
                if logger.isEnabledFor(logger.DEBUG):
                    logger.debug(f"[Music] Guild ID: {guild_id}, file deletion successful!")
        except Exception as e:
            logger.warning(f"[Music] Guild ID: {guild_id}, file deletion failed: {e}")
            
    async def cleanup_guild_files(self, guild_id: int, folder: str):
        """Clean up all audio files for a guild"""
        for file in os.listdir(folder):
            file_path = os.path.join(folder, file)
            await self.delete_file(guild_id, file_path)
