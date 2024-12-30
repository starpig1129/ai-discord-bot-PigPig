import os
import logging as logger
import subprocess
import asyncio
import yt_dlp
from youtube_search import YoutubeSearch

def check_ffmpeg():
    """Check if FFmpeg is available and working"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("FFmpeg is not available or not working properly")
        return False

class YouTubeManager:
    def __init__(self, time_limit=1800):  # 30分鐘限制
        self.time_limit = time_limit
        if not check_ffmpeg():
            raise RuntimeError("FFmpeg is required but not available")

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
                'format': 'bestaudio[ext=m4a]/bestaudio/best',  # Prefer M4A format for better compatibility
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
            
            # Ensure the output directory exists and is writable
            if not os.access(folder, os.W_OK):
                logger.error(f"Output directory {folder} is not writable")
                return None, "無法寫入下載目錄"

            # Check available disk space (require at least 100MB)
            try:
                statvfs = os.statvfs(folder)
                available_space = statvfs.f_frsize * statvfs.f_bavail
                if available_space < 100 * 1024 * 1024:  # 100MB
                    logger.error(f"Insufficient disk space in {folder}")
                    return None, "磁碟空間不足"
            except Exception as e:
                logger.error(f"Failed to check disk space: {e}")
                
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': output_template,
                'noplaylist': True,
                'quiet': False,
                'no_warnings': False,
                'extract_flat': False,
                'force_generic_extractor': False,
                'ffmpeg_location': '/usr/bin/ffmpeg',
                'postprocessor_args': [
                    '-threads', '2',  # Reduced thread count to prevent overload
                    '-loglevel', 'warning',
                    '-y',  # Overwrite output files
                    '-max_muxing_queue_size', '2048',  # Increased buffer size
                    '-analyzeduration', '20M',  # Increased analysis time
                    '-probesize', '20M',  # Increased probe size
                    '-reconnect', '1',  # Enable reconnection
                    '-reconnect_streamed', '1',
                    '-reconnect_delay_max', '30',  # Maximum delay between reconnections
                    '-timeout', '30000000',  # Timeout in microseconds (30 seconds)
                    '-rw_timeout', '30000000'  # Read/write timeout
                ],
                'socket_timeout': 300,  # Increased timeout
                'retries': 10,  # Increased retries
                'verbose': True,
                'progress_hooks': [lambda d: logger.info(f"Download progress: {d.get('status', 'unknown')} - {d.get('_percent_str', '0%')}")],
                'merge_output_format': 'mp3',
                'concurrent_fragment_downloads': 1,  # Limit concurrent downloads
                'file_access_retries': 5,  # Retry file access operations
                'fragment_retries': 10,  # Retry fragment downloads
                'retry_sleep_functions': {'http': lambda n: 5},  # Wait 5 seconds between retries
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Sec-Fetch-Mode': 'navigate'
                }
            }

            logger.info(f"[音樂] 開始下載 (ID: {interaction.guild.id}): {url} 到 {folder}")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)

                # 檢查時長限制
                if info_dict.get('duration', 0) > self.time_limit:
                    logger.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, 影片時間過長！")
                    return None, "影片時間過長！超過 30 分鐘"

                try:
                    # 下載音訊
                    logger.info(f"[音樂] 開始下載過程 (ID: {interaction.guild.id}): {url}")
                    
                    # Add retry logic for the download
                    max_retries = 3
                    retry_count = 0
                    while retry_count < max_retries:
                        try:
                            ydl.download([url])
                            logger.info(f"[音樂] 下載完成 (ID: {interaction.guild.id}): {url}")
                            break
                        except Exception as download_error:
                            retry_count += 1
                            if retry_count >= max_retries:
                                raise download_error
                            logger.warning(f"[音樂] 下載重試 {retry_count}/{max_retries}: {str(download_error)}")
                            await asyncio.sleep(2)  # Wait before retrying
                    
                    # Verify the output file exists and is not empty
                    file_path = os.path.join(folder, f"{info_dict['id']}.mp3")
                    if not os.path.exists(file_path):
                        raise Exception("Output file is missing")
                    if os.path.getsize(file_path) == 0:
                        raise Exception("Output file is empty")
                    
                    # Verify the file is a valid MP3
                    try:
                        subprocess.run(['ffmpeg', '-v', 'error', '-i', file_path, '-f', 'null', '-'],
                                    check=True, capture_output=True)
                    except subprocess.CalledProcessError as e:
                        raise Exception(f"Invalid MP3 file: {e.stderr.decode()}")
                except Exception as e:
                    logger.error(f"[音樂] 下載過程出錯: {str(e)}")
                    # Clean up any partially downloaded files
                    try:
                        partial_file = os.path.join(folder, f"{info_dict['id']}")
                        if os.path.exists(partial_file):
                            os.remove(partial_file)
                        if os.path.exists(f"{partial_file}.mp3"):
                            os.remove(f"{partial_file}.mp3")
                    except Exception as cleanup_error:
                        logger.error(f"[音樂] 清理檔案失敗: {str(cleanup_error)}")
                    raise

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
