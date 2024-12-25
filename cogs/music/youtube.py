import os
import logging as logger
from pytubefix import YouTube, Playlist
from youtube_search import YoutubeSearch
import random

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

    async def download_playlist(self, url, folder, interaction):
        """下載YouTube播放清單的音訊"""
        try:
            playlist = Playlist(url)
            video_infos = []
            
            # 只下載前5首歌曲，其他的等待後續下載
            for video_url in playlist.video_urls[:5]:
                video_info, error = await self.download_audio(video_url, folder, interaction)
                if video_info:
                    video_infos.append(video_info)
                    
            # 保存剩餘歌曲的URL
            remaining_urls = playlist.video_urls[5:]
            remaining_infos = []
            
            # 獲取剩餘歌曲的基本信息（不下載）
            for video_url in remaining_urls:
                try:
                    yt = YouTube(video_url)
                    video_info = {
                        "url": video_url,
                        "title": yt.title,
                        "duration": yt.length,
                        "video_id": yt.video_id,
                        "author": yt.author,
                        "views": yt.views,
                        "requester": interaction.user,
                        "user_avatar": interaction.user.avatar.url
                    }
                    remaining_infos.append(video_info)
                except Exception as e:
                    logger.error(f"[音樂] 獲取影片信息失敗: {e}")
                    continue
            
            video_infos.extend(remaining_infos)
            return video_infos, None
            
        except Exception as e:
            logger.error(f"[音樂] 播放清單下載失敗: {e}")
            return None, "播放清單下載失敗"

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
