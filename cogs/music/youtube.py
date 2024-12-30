import os
import logging as logger
import yt_dlp
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

    async def download_playlist(self, url, folder, interaction):
        """下載YouTube播放清單的音訊"""
        try:
            # Ensure download directory exists
            os.makedirs(folder, exist_ok=True)
            
            # Use mp3 extension directly since we're converting to mp3
            output_template = os.path.join(folder, '%(id)s.mp3')
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': output_template,
                'noplaylist': False,
                'extract_flat': True,  # 僅提取播放清單資訊，不下載
                'quiet': True,
                'no_warnings': True,
                'force_generic_extractor': False
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)
                if 'entries' not in info_dict:
                    logger.error("[音樂] 無法獲取播放清單資訊")
                    return None, "無法獲取播放清單資訊"

                video_infos = []
                remaining_infos = []
                
                # 只下載第一首歌曲
                if info_dict['entries']:
                    first_entry = info_dict['entries'][0]
                    video_url = first_entry['url']
                    video_info, error = await self.download_audio(video_url, folder, interaction)
                    if video_info:
                        video_infos.append(video_info)

                # 獲取其他歌曲的基本信息（不下載）
                for entry in info_dict['entries'][1:]:
                    video_info = {
                        "url": entry['url'],
                        "title": entry.get('title', '未知標題'),
                        "duration": entry.get('duration', 0),
                        "video_id": entry.get('id', '未知ID'),
                        "author": entry.get('uploader', '未知上傳者'),
                        "views": entry.get('view_count', 0),
                        "requester": interaction.user,
                        "user_avatar": interaction.user.avatar.url,
                        "file_path": None  # 尚未下載
                    }
                    remaining_infos.append(video_info)

                video_infos.extend(remaining_infos)
                return video_infos, None

        except Exception as e:
            logger.error(f"[音樂] 播放清單下載失敗: {e}")
            return None, "播放清單下載失敗"

    async def get_video_info_without_download(self, url, interaction):
        """獲取影片資訊但不下載"""
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'force_generic_extractor': False
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)

                # 檢查時長限制
                if info_dict.get('duration', 0) > self.time_limit:
                    logger.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, 影片時間過長！")
                    return None, "影片時間過長！超過 30 分鐘"

                # 返回影片資訊
                video_info = {
                    "file_path": None,  # 尚未下載
                    "title": info_dict.get('title', '未知標題'),
                    "url": url,
                    "duration": info_dict.get('duration', 0),
                    "video_id": info_dict.get('id', '未知ID'),
                    "author": info_dict.get('uploader', '未知上傳者'),
                    "views": info_dict.get('view_count', 0),
                    "requester": interaction.user,
                    "user_avatar": interaction.user.avatar.url
                }

                return video_info, None

        except Exception as e:
            logger.error(f"[音樂] 獲取資訊失敗: {e}")
            return None, "獲取資訊失敗"

    async def download_audio(self, url, folder, interaction):
        """下載YouTube影片的音訊"""
        try:
            # Ensure download directory exists
            os.makedirs(folder, exist_ok=True)
            
            # Use mp3 extension directly since we're converting to mp3
            output_template = os.path.join(folder, '%(id)s')
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': output_template,
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'force_generic_extractor': False
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)

                # 檢查時長限制
                if info_dict.get('duration', 0) > self.time_limit:
                    logger.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, 影片時間過長！")
                    return None, "影片時間過長！超過 30 分鐘"

                # 下載音訊
                ydl.download([url])

                # Use mp3 extension since we're converting to mp3
                file_path = os.path.join(folder, f"{info_dict['id']}.mp3")

                # 返回影片資訊
                video_info = {
                    "file_path": file_path,
                    "title": info_dict.get('title', '未知標題'),
                    "url": url,
                    "duration": info_dict.get('duration', 0),
                    "video_id": info_dict.get('id', '未知ID'),
                    "author": info_dict.get('uploader', '未知上傳者'),
                    "views": info_dict.get('view_count', 0),
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
