import os
import logging as logger
import subprocess
import asyncio
import yt_dlp
from youtube_search import YoutubeSearch

async def check_ffmpeg():
    """檢查 FFmpeg 是否可用且能正常運作"""
    try:
        # 使用 asyncio.to_thread 非同步執行 FFmpeg 檢查
        await asyncio.to_thread(
            lambda: subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("FFmpeg 無法使用或運作異常")
        return False

class YouTubeManager:
    def __init__(self, time_limit=1800):  # 30 分鐘限制
        self.time_limit = time_limit
        
    @classmethod
    async def create(cls, time_limit=1800):
        """Create and initialize a new YouTubeManager instance"""
        if not await check_ffmpeg():
            raise RuntimeError("系統需要 FFmpeg，但目前無法使用")
        manager = cls(time_limit)
        return manager

    async def search_videos(self, query, max_results=10):
        """搜尋 YouTube 影片"""
        try:
            # 使用 asyncio.to_thread 非同步執行搜尋
            results = await asyncio.to_thread(
                lambda: YoutubeSearch(query, max_results=max_results).to_dict()
            )
            
            # Add complete URL and ensure all required fields
            for result in results:
                result['url'] = f"https://youtube.com/watch?v={result['id']}"
                result['video_id'] = result['id']  # Ensure video_id is set
                result['author'] = result.get('channel', '未知上傳者')  # Map channel to author
                result['views'] = result.get('views', '0')  # Ensure views exists
                # Convert duration string (e.g. "3:21") to seconds
                if 'duration' in result:
                    try:
                        parts = result['duration'].split(':')
                        if len(parts) == 2:  # MM:SS
                            result['duration'] = int(parts[0]) * 60 + int(parts[1])
                        elif len(parts) == 3:  # HH:MM:SS
                            result['duration'] = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                        else:
                            result['duration'] = 0
                    except (ValueError, IndexError):
                        result['duration'] = 0
                else:
                    result['duration'] = 0
                
            return results if results else []
        except Exception as e:
            logger.error(f"YouTube 搜尋失敗: {e}")
            return []

    async def download_playlist(self, url, folder, interaction):
        """下載 YouTube 播放清單的音訊"""
        try:
            # 非同步確保下載資料夾存在
            await asyncio.to_thread(os.makedirs, folder, exist_ok=True)
            
            # 因為要轉成 mp3 格式，所以直接使用 mp3 副檔名
            output_template = os.path.join(folder, '%(id)s.mp3')
            
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',  # 優先選擇 M4A 格式，以取得較佳相容性
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

            # 使用 asyncio.to_thread 非同步執行 yt-dlp 資訊提取
            async def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            info_dict = await extract_info()
            if 'entries' not in info_dict:
                logger.error("[音樂] 無法取得播放清單資訊")
                return None, "無法取得播放清單資訊"

            video_infos = []
            remaining_infos = []
            
            # 使用 asyncio.gather 同時處理第一首歌曲的下載和其他歌曲的資訊獲取
            if info_dict['entries']:
                first_entry = info_dict['entries'][0]
                video_url = first_entry['url']
                
                # 準備其他歌曲的資訊
                other_songs_info = [
                    {
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
                    for entry in info_dict['entries'][1:]
                ]
                
                # 同時執行下載和資訊處理
                first_song_download = self.download_audio(video_url, folder, interaction)
                first_song_info, error = await first_song_download
                
                if first_song_info:
                    video_infos.append(first_song_info)
                remaining_infos.extend(other_songs_info)

            video_infos.extend(remaining_infos)
            return video_infos, None

        except Exception as e:
            logger.error(f"[音樂] 播放清單下載失敗: {e}")
            return None, "播放清單下載失敗"

    async def get_video_info_without_download(self, url, interaction):
        """僅取得影片資訊，而不執行下載"""
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'playlist_items': '1-50',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'force_generic_extractor': False
            }

            # 使用 asyncio.to_thread 非同步執行 yt-dlp 資訊提取
            async def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            info_dict = await extract_info()

            # 檢查影片時長是否超過限制
            if info_dict.get('duration', 0) > self.time_limit:
                logger.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, 影片時長過長！")
                return None, "影片時長過長！超過 30 分鐘"

            # 回傳影片資訊
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
            logger.error(f"[音樂] 取得影片資訊失敗: {e}")
            return None, "取得影片資訊失敗"

    async def download_audio(self, url, folder, interaction):
        """下載 YouTube 影片的音訊"""
        try:
            # 非同步確保下載資料夾存在
            await asyncio.to_thread(os.makedirs, folder, exist_ok=True)
            
            # 因為要轉成 mp3 格式，所以直接使用 mp3 副檔名
            output_template = os.path.join(folder, '%(id)s')
            
            # 非同步檢查輸出資料夾是否可寫入
            if not await asyncio.to_thread(os.access, folder, os.W_OK):
                logger.error(f"無法寫入下載目錄: {folder}")
                return None, "無法寫入下載目錄"

            # 非同步檢查可用磁碟空間
            try:
                statvfs = await asyncio.to_thread(os.statvfs, folder)
                available_space = statvfs.f_frsize * statvfs.f_bavail
                if available_space < 100 * 1024 * 1024:  # 100MB
                    logger.error(f"磁碟空間不足: {folder}")
                    return None, "磁碟空間不足"
            except Exception as e:
                logger.error(f"檢查磁碟空間失敗: {e}")
                
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'playlist_items': '1-50',
                'outtmpl': output_template,
                'noplaylist': True,
                'quiet': False,
                'no_warnings': False,
                'extract_flat': False,
                'force_generic_extractor': False,
                'ffmpeg_location': '/usr/bin/ffmpeg',
                'postprocessor_args': [
                    '-threads', '2',  # 降低執行緒數量以避免過載
                    '-loglevel', 'warning',
                    '-y',  # 覆蓋輸出檔案
                    '-max_muxing_queue_size', '2048',  # 擴增緩衝區大小
                    '-analyzeduration', '20M',  # 增加分析時間
                    '-probesize', '20M',  # 增加探測大小
                    '-reconnect', '1',  # 啟用重新連線
                    '-reconnect_streamed', '1',
                    '-reconnect_delay_max', '30',  # 重新連線間的最長延遲
                    '-timeout', '30000000',  # 超時設定 (微秒) (此處約 30 秒)
                    '-rw_timeout', '30000000'  # 讀寫超時
                ],
                'socket_timeout': 300,  # 延長連線超時時間
                'retries': 10,  # 提高重試次數
                'verbose': False,
                'progress_hooks': [lambda d: logger.info(f"下載進度: {d.get('status', 'unknown')} - {d.get('_percent_str', '0%')}")],
                'merge_output_format': 'mp3',
                'concurrent_fragment_downloads': 1,  # 限制同時下載的片段數
                'file_access_retries': 5,  # 檔案存取的重試次數
                'fragment_retries': 10,  # 片段下載的重試次數
                'retry_sleep_functions': {'http': lambda n: 5},  # 重試間隔 5 秒
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Sec-Fetch-Mode': 'navigate'
                }
            }

            logger.info(f"[音樂] 開始下載 (伺服器 ID: {interaction.guild.id}): {url} 到 {folder}")

            # 使用 asyncio.to_thread 非同步執行 yt-dlp 資訊提取
            async def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            info_dict = await extract_info()

            # 檢查影片時長是否超過限制
            if info_dict.get('duration', 0) > self.time_limit:
                logger.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, 影片時長過長！")
                return None, "影片時長過長！超過 30 分鐘"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    # 執行下載音訊
                    logger.info(f"[音樂] 正在開始下載 (伺服器 ID: {interaction.guild.id}): {url}")
                    
                    # 新增簡易重試機制
                    max_retries = 3
                    retry_count = 0
                    while retry_count < max_retries:
                        try:
                            # 非同步執行下載
                            await asyncio.to_thread(ydl.download, [url])
                            logger.info(f"[音樂] 下載完成 (伺服器 ID: {interaction.guild.id}): {url}")
                            break
                        except Exception as download_error:
                            retry_count += 1
                            if retry_count >= max_retries:
                                raise download_error
                            logger.warning(f"[音樂] 下載失敗，嘗試重新下載 {retry_count}/{max_retries} 次: {str(download_error)}")
                            await asyncio.sleep(2)  # 重試前先停頓數秒
                    
                    # 非同步驗證輸出檔案
                    file_path = os.path.join(folder, f"{info_dict['id']}.mp3")
                    exists = await asyncio.to_thread(os.path.exists, file_path)
                    if not exists:
                        raise Exception("輸出檔案不存在")
                    
                    size = await asyncio.to_thread(os.path.getsize, file_path)
                    if size == 0:
                        raise Exception("輸出檔案為空")

                    # 非同步驗證 MP3 格式
                    try:
                        await asyncio.to_thread(
                            lambda: subprocess.run(
                                ['ffmpeg', '-v', 'error', '-i', file_path, '-f', 'null', '-'],
                                check=True, capture_output=True
                            )
                        )
                    except subprocess.CalledProcessError as e:
                        raise Exception(f"檔案不是有效的 MP3 格式: {e.stderr.decode()}")

                    # 回傳影片資訊
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
                    logger.error(f"[音樂] 下載過程發生錯誤: {str(e)}")
                    # 如果只下載到部分檔案，嘗試進行清理
                    try:
                        partial_file = os.path.join(folder, f"{info_dict['id']}")
                        # 非同步清理檔案
                        async def clean_file(path):
                            if await asyncio.to_thread(os.path.exists, path):
                                await asyncio.to_thread(os.remove, path)
                        
                        await asyncio.gather(
                            clean_file(partial_file),
                            clean_file(f"{partial_file}.mp3")
                        )
                    except Exception as cleanup_error:
                        logger.error(f"[音樂] 無法清理部分下載檔案: {str(cleanup_error)}")
                    raise

        except Exception as e:
            logger.error(f"[音樂] 下載失敗: {e}")
            return None, "下載失敗"

    def get_thumbnail_url(self, video_id):
        """取得影片縮圖 URL"""
        return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
