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
        """根據歌曲資訊建立 FFmpeg 音訊來源"""
        is_live = song.get('is_live', False)
        
        if is_live:
            stream_url = song.get('stream_url')
            if not stream_url:
                raise ValueError("直播歌曲缺少 stream_url")
            
            # 針對直播優化的 FFmpeg 參數
            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn'
            }
            return FFmpegPCMAudio(stream_url, **ffmpeg_options)
        else:
            file_path = song.get('file_path')
            if not file_path or not os.path.exists(file_path):
                raise ValueError(f"音訊檔案不存在或路徑錯誤: {file_path}")
            
            # 針對本地檔案的標準參數
            return FFmpegPCMAudio(file_path)
        
    async def delete_file(self, guild_id: int, file_path: str):
        """Non-blocking file deletion using asyncio.to_thread"""
        try:
            if os.path.exists(file_path):
                await asyncio.to_thread(os.remove, file_path)
                if logger.isEnabledFor(logger.DEBUG):
                    logger.debug(f"[音樂] Guild ID: {guild_id}, file deletion successful!")
        except Exception as e:
            logger.warning(f"[音樂] Guild ID: {guild_id}, file deletion failed: {e}")
            
    async def cleanup_guild_files(self, guild_id: int, folder: str):
        """Clean up all audio files for a guild"""
        for file in os.listdir(folder):
            file_path = os.path.join(folder, file)
            await self.delete_file(guild_id, file_path)
