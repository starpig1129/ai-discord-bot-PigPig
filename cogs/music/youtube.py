import os
import logging as logger
from pytubefix import YouTube
from youtube_search import YoutubeSearch

class YouTubeManager:
    def __init__(self, time_limit=1800):  # 30分鐘限制
        self.time_limit = time_limit

    async def search_videos(self, query, max_results=10):
        """搜尋YouTube影片"""
        try:
            results = YoutubeSearch(query, max_results=max_results).to_dict()
            return results if results else []
        except Exception as e:
            logger.error(f"YouTube搜尋失敗: {e}")
            return []

    async def download_audio(self, url, folder, interaction):
        """下載YouTube影片的音訊"""
        try:
            yt = YouTube(url)
            
            # 檢查時長限制
            if yt.length > self.time_limit:
                logger.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, 影片時間過長！")
                return None, "影片時間過長！超過 30 分鐘"

            audio_stream = yt.streams.get_audio_only()
            file_path = os.path.join(folder, f"{yt.video_id}.mp3")

            # 避免重複下載
            if not os.path.exists(file_path):
                audio_stream.download(output_path=folder, filename=f"{yt.video_id}.mp3")

            # 返回影片資訊
            video_info = {
                "file_path": file_path,
                "title": yt.title,
                "url": url,
                "duration": yt.length,
                "video_id": yt.video_id,
                "author": yt.author,
                "views": yt.views,
                "requester": interaction.user,
                "user_avatar": interaction.user.avatar.url
            }
            
            return video_info, None

        except Exception as e:
            logger.error(f"[音樂] 下載失敗: {e}")
            return None, "下載失敗"

    def get_thumbnail_url(self, video_id):
        """獲取影片縮圖URL"""
        return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
