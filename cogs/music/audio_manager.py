import os
import asyncio
import logging as logger
from discord import FFmpegPCMAudio

class AudioManager:
    def __init__(self):
        self.current_audio = None
        
    def create_audio_source(self, file_path: str) -> FFmpegPCMAudio:
        """Create a new FFmpeg audio source"""
        return FFmpegPCMAudio(file_path)
        
    async def delete_file(self, guild_id: int, file_path: str):
        """Non-blocking file deletion using asyncio.to_thread"""
        try:
            if os.path.exists(file_path):
                await asyncio.to_thread(os.remove, file_path)
                if logger.getLogger().isEnabledFor(logger.DEBUG):
                    logger.debug(f"[音樂] 伺服器 ID： {guild_id}, 刪除檔案成功！")
        except Exception as e:
            logger.warning(f"[音樂] 伺服器 ID： {guild_id}, 刪除檔案失敗： {e}")
            
    async def cleanup_guild_files(self, guild_id: int, folder: str):
        """Clean up all audio files for a guild"""
        for file in os.listdir(folder):
            file_path = os.path.join(folder, file)
            await self.delete_file(guild_id, file_path)
