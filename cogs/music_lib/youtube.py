import os
import logging as logger
import subprocess
import asyncio
import yt_dlp
import discord
import random
import re
from youtube_search import YoutubeSearch
from addons.settings import Settings

async def check_ffmpeg(ffmpeg_path='/usr/bin/ffmpeg'):
    """檢查 FFmpeg 是否可用且能正常運作"""
    try:
        # 使用 asyncio.to_thread 非同步執行 FFmpeg 檢查
        await asyncio.to_thread(
            lambda: subprocess.run([ffmpeg_path, '-version'], capture_output=True, check=True)
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error(f"FFmpeg 無法使用或運作異常: {ffmpeg_path}")
        return False

class YouTubeManager:
    def __init__(self, time_limit=1800):  # 30 分鐘限制
        self.time_limit = time_limit
        # 載入 FFmpeg 設定
        try:
            self.settings = Settings()
            self.ffmpeg_config = self.settings.ffmpeg
        except Exception as e:
            logger.error(f"載入 FFmpeg 設定失敗，使用預設值: {e}")
            # 使用預設 FFmpeg 設定
            self.ffmpeg_config = self._get_default_ffmpeg_config()
    
    def _get_default_ffmpeg_config(self) -> dict:
        """獲取預設 FFmpeg 設定"""
        return {
            "location": "/usr/bin/ffmpeg",
            "audio_quality": "192",
            "audio_codec": "mp3",
            "postprocessor_args": {
                "threads": 2,
                "loglevel": "warning",
                "overwrite_output": True,
                "max_muxing_queue_size": 2048,
                "analyzeduration": "20M",
                "probesize": "20M",
                "reconnect": True,
                "reconnect_streamed": True,
                "reconnect_delay_max": 30,
                "timeout": 30000000,
                "rw_timeout": 30000000
            },
            "ytdlp_options": {
                "socket_timeout": 300,
                "retries": 10,
                "concurrent_fragment_downloads": 1,
                "file_access_retries": 5,
                "fragment_retries": 10,
                "retry_sleep_http": 5
            },
            "http_headers": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept_language": "en-us,en;q=0.5",
                "sec_fetch_mode": "navigate"
            }
        }
    
    def _build_postprocessor_args(self) -> list:
        """根據設定構建 FFmpeg postprocessor 參數"""
        args = []
        pp_config = self.ffmpeg_config.get("postprocessor_args", {})
        
        # 執行緒數
        if "threads" in pp_config:
            args.extend(["-threads", str(pp_config["threads"])])
        
        # 日誌等級
        if "loglevel" in pp_config:
            args.extend(["-loglevel", pp_config["loglevel"]])
        
        # 覆蓋輸出檔案
        if pp_config.get("overwrite_output", False):
            args.append("-y")
        
        # 其他參數
        for key, value in pp_config.items():
            if key in ["threads", "loglevel", "overwrite_output"]:
                continue
                
            if isinstance(value, bool):
                if value:
                    args.extend([f"-{key}", "1"])
            else:
                args.extend([f"-{key}", str(value)])
        
        return args
        
    @classmethod
    async def create(cls, time_limit=1800):
        """Create and initialize a new YouTubeManager instance"""
        manager = cls(time_limit)
        ffmpeg_path = manager.ffmpeg_config.get('location', '/usr/bin/ffmpeg')
        if not await check_ffmpeg(ffmpeg_path):
            raise RuntimeError(f"系統需要 FFmpeg，但目前無法使用: {ffmpeg_path}")
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
                        # If duration is already an integer, use it directly
                        if isinstance(result['duration'], int):
                            pass
                        # If it's a string, try to parse it
                        elif isinstance(result['duration'], str):
                            parts = result['duration'].split(':')
                            if len(parts) == 2:  # MM:SS
                                result['duration'] = int(parts[0]) * 60 + int(parts[1])
                            elif len(parts) == 3:  # HH:MM:SS
                                result['duration'] = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                            else:
                                result['duration'] = 0
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
                    'preferredcodec': self.ffmpeg_config.get('audio_codec', 'mp3'),
                    'preferredquality': self.ffmpeg_config.get('audio_quality', '192'),
                }],
                'outtmpl': output_template,
                'noplaylist': False,
                'extract_flat': True,  # 僅提取播放清單資訊，不下載
                'quiet': True,
                'no_warnings': True,
                'force_generic_extractor': False,
                'ffmpeg_location': self.ffmpeg_config.get('location', '/usr/bin/ffmpeg')
            }

            # 檢查並加入 cookies
            cookies_path = self.settings.youtube_cookies_path
            if os.path.exists(cookies_path):
                logger.info(f"使用 Cookies 檔案: {cookies_path}")
                ydl_opts['cookiefile'] = cookies_path

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
                        "file_path": None,  # 尚未下載
                        "is_live": entry.get('is_live', False) # 檢查是否為直播
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
                    'preferredcodec': self.ffmpeg_config.get('audio_codec', 'mp3'),
                    'preferredquality': self.ffmpeg_config.get('audio_quality', '192'),
                }],
                'playlist_items': '1-50',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'force_generic_extractor': False,
                'ffmpeg_location': self.ffmpeg_config.get('location', '/usr/bin/ffmpeg')
            }

            # 檢查並加入 cookies
            cookies_path = self.settings.youtube_cookies_path
            if os.path.exists(cookies_path):
                logger.info(f"使用 Cookies 檔案: {cookies_path}")
                ydl_opts['cookiefile'] = cookies_path

            # 使用 asyncio.to_thread 非同步執行 yt-dlp 資訊提取
            async def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            info_dict = await extract_info()

            # 檢查是否為直播
            is_live = info_dict.get('is_live', False)

            # 如果不是直播，才檢查影片時長
            if not is_live and info_dict.get('duration', 0) > self.time_limit:
                logger.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, 影片時長過長！")
                return None, "影片時長過長！超過 30 分鐘"

            # 回傳影片資訊
            video_info = {
                "file_path": None,  # 尚未下載
                "title": info_dict.get('title', '未知標題'),
                "url": info_dict.get('webpage_url', url),
                "stream_url": info_dict.get('url') if is_live else None,
                "duration": info_dict.get('duration', 0),
                "video_id": info_dict.get('id', '未知ID'),
                "author": info_dict.get('uploader', '未知上傳者'),
                "views": info_dict.get('view_count', 0),
                "requester": interaction.user,
                "user_avatar": interaction.user.avatar.url,
                "is_live": is_live
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
                
            # 從設定構建 ydl_opts
            ytdlp_config = self.ffmpeg_config.get('ytdlp_options', {})
            http_headers = self.ffmpeg_config.get('http_headers', {})
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.ffmpeg_config.get('audio_codec', 'mp3'),
                    'preferredquality': self.ffmpeg_config.get('audio_quality', '192'),
                }],
                'playlist_items': '1-50',
                'outtmpl': output_template,
                'noplaylist': True,
                'quiet': False,
                'no_warnings': False,
                'extract_flat': False,
                'force_generic_extractor': False,
                'ffmpeg_location': self.ffmpeg_config.get('location', '/usr/bin/ffmpeg'),
                'postprocessor_args': self._build_postprocessor_args(),
                'socket_timeout': ytdlp_config.get('socket_timeout', 300),
                'retries': ytdlp_config.get('retries', 10),
                'verbose': False,
                'progress_hooks': [lambda d: logger.debug(f"下載進度: {d.get('status', 'unknown')} - {d.get('_percent_str', '0%')}")],
                'merge_output_format': self.ffmpeg_config.get('audio_codec', 'mp3'),
                'concurrent_fragment_downloads': ytdlp_config.get('concurrent_fragment_downloads', 1),
                'file_access_retries': ytdlp_config.get('file_access_retries', 5),
                'fragment_retries': ytdlp_config.get('fragment_retries', 10),
                'retry_sleep_functions': {'http': lambda n: ytdlp_config.get('retry_sleep_http', 5)},
                'http_headers': {
                    'User-Agent': http_headers.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'),
                    'Accept': http_headers.get('accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
                    'Accept-Language': http_headers.get('accept_language', 'en-us,en;q=0.5'),
                    'Sec-Fetch-Mode': http_headers.get('sec_fetch_mode', 'navigate')
                }
            }

            # 檢查並加入 cookies
            cookies_path = self.settings.youtube_cookies_path
            if os.path.exists(cookies_path):
                logger.info(f"使用 Cookies 檔案: {cookies_path}")
                ydl_opts['cookiefile'] = cookies_path

            logger.info(f"[音樂] 開始下載 (伺服器 ID: {interaction.guild.id}): {url} 到 {folder}")

            # 使用 asyncio.to_thread 非同步執行 yt-dlp 資訊提取
            async def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            info_dict = await extract_info()

            # 檢查是否為直播
            is_live = info_dict.get('is_live', False)

            # 如果是直播，直接回傳資訊，不進行下載
            if is_live:
                logger.info(f"[音樂] 偵測到直播影片 (伺服器 ID: {interaction.guild.id}): {url}")
                video_info = {
                    "file_path": None,  # 直播沒有本地檔案路徑
                    "title": info_dict.get('title', '未知標題'),
                    "url": info_dict.get('webpage_url', url),
                    "stream_url": info_dict.get('url'), # 直播流 URL
                    "duration": 0,  # 直播沒有固定時長
                    "video_id": info_dict.get('id', '未知ID'),
                    "author": info_dict.get('uploader', '未知上傳者'),
                    "views": info_dict.get('view_count', 0),
                    "requester": interaction.user,
                    "user_avatar": interaction.user.avatar.url,
                    "is_live": True
                }
                return video_info, None

            # 如果不是直播，才檢查影片時長
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
                        ffmpeg_path = self.ffmpeg_config.get('location', '/usr/bin/ffmpeg')
                        await asyncio.to_thread(
                            lambda: subprocess.run(
                                [ffmpeg_path, '-v', 'error', '-i', file_path, '-f', 'null', '-'],
                                check=True, capture_output=True
                            )
                        )
                    except subprocess.CalledProcessError as e:
                        raise Exception(f"檔案不是有效的 MP3 格式: {e.stderr.decode()}")

                    # 回傳影片資訊
                    video_info = {
                        "file_path": file_path,
                        "title": info_dict.get('title', '未知標題'),
                        "url": info_dict.get('webpage_url', url),
                        "stream_url": None, # 非直播
                        "duration": info_dict.get('duration', 0),
                        "video_id": info_dict.get('id', '未知ID'),
                        "author": info_dict.get('uploader', '未知上傳者'),
                        "views": info_dict.get('view_count', 0),
                        "requester": interaction.user,
                        "user_avatar": interaction.user.avatar.url,
                        "is_live": False
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

    async def get_related_videos(self, video_id: str, title: str, author: str, interaction: discord.Interaction, limit: int = 5, exclude_ids: set = None):
        """
        使用多層次策略獲取相關影片列表，並過濾掉 exclude_ids 中的影片。

        策略:
        1. 基於藝人/頻道搜尋。
        2. 基於淨化後的標題搜尋。
        3. 使用 yt-dlp 的 'up next' 列表作為備用。
        """
        if exclude_ids is None:
            exclude_ids = set()
        
        final_results = []
        # 確保當前影片ID也被排除
        exclude_ids.add(video_id)

        # 輔助函式來處理和格式化搜尋結果
        def process_search_results(results):
            processed = []
            for video in results:
                video_id_res = video.get('video_id')
                if video_id_res and video_id_res not in exclude_ids:
                    processed.append({
                        "file_path": None,
                        "title": video.get('title', '未知標題'),
                        "url": video.get('url'),
                        "stream_url": None,
                        "duration": video.get('duration', 0),
                        "video_id": video_id_res,
                        "author": video.get('author', '未知上傳者'),
                        "views": video.get('views', 0),
                        "requester": interaction.user,
                        "user_avatar": interaction.user.avatar.url,
                        "is_live": False
                    })
                    exclude_ids.add(video_id_res)
            return processed

        # --- 策略一: 基於藝人/頻道的搜尋 ---
        if author and author != '未知上傳者':
            logger.info(f"策略一: 正在為藝人 '{author}' 搜尋歌曲...")
            try:
                # 嘗試兩種搜尋查詢
                queries = [f"{author} songs", author]
                author_results = []
                for query in queries:
                    if len(author_results) >= limit:
                        break
                    results = await self.search_videos(query, max_results=limit + 10)
                    author_results.extend(process_search_results(results))
                
                if author_results:
                    # 增加隨機性
                    num_to_add = min(limit - len(final_results), len(author_results))
                    final_results.extend(random.sample(author_results, num_to_add))
                    logger.info(f"策略一找到 {len(final_results)} 首歌曲。")

            except Exception as e:
                logger.error(f"策略一 (藝人搜尋) 失敗: {e}")

        # --- 策略二: 基於淨化標題的搜尋 ---
        if len(final_results) < limit:
            logger.info("策略二: 正在使用淨化標題進行搜尋...")
            try:
                # 移除標題中的雜訊
                clean_title = re.sub(r'\s*\(.*?(official|video|lyric|mv|audio|4k|hd).*?\)\s*|\[.*?\]', '', title, flags=re.IGNORECASE).strip()
                if not clean_title or len(clean_title) < 3:
                    clean_title = title # 如果淨化後標題太短，則使用原標題
                
                logger.info(f"原始標題: '{title}', 淨化後標題: '{clean_title}'")
                
                results = await self.search_videos(clean_title, max_results=limit + 10)
                title_results = process_search_results(results)

                if title_results:
                    num_to_add = min(limit - len(final_results), len(title_results))
                    if num_to_add > 0:
                        final_results.extend(random.sample(title_results, num_to_add))
                        logger.info(f"策略二新增了 {num_to_add} 首歌曲。")

            except Exception as e:
                logger.error(f"策略二 (標題搜尋) 失敗: {e}")

        # --- 策略三: yt-dlp 'up next' (備用) ---
        if len(final_results) < limit:
            logger.info("策略三: 正在使用 yt-dlp 'up next' 作為備用方案...")
            try:
                ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'no_warnings': True, 'extract_flat': True}
                cookies_path = self.settings.youtube_cookies_path
                if os.path.exists(cookies_path):
                    ydl_opts['cookiefile'] = cookies_path
                
                url = f"https://www.youtube.com/watch?v={video_id}"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                    if 'entries' in info and info['entries']:
                        yt_dlp_results = []
                        for entry in info['entries']:
                            entry_id = entry.get('id')
                            if entry_id and entry_id not in exclude_ids and not entry.get('is_live') and entry.get('ie_key') == 'Youtube':
                                yt_dlp_results.append({
                                    "file_path": None, "title": entry.get('title', '未知標題'),
                                    "url": f"https://www.youtube.com/watch?v={entry_id}",
                                    "stream_url": None, "duration": entry.get('duration', 0),
                                    "video_id": entry_id, "author": entry.get('uploader', '未知上傳者'),
                                    "views": entry.get('view_count', 0), "requester": interaction.user,
                                    "user_avatar": interaction.user.avatar.url, "is_live": False
                                })
                                exclude_ids.add(entry_id)
                        
                        num_to_add = min(limit - len(final_results), len(yt_dlp_results))
                        if num_to_add > 0:
                            final_results.extend(random.sample(yt_dlp_results, num_to_add))
                            logger.info(f"策略三新增了 {num_to_add} 首歌曲。")
            
            except Exception as e:
                logger.error(f"策略三 (yt-dlp) 失敗: {e}")

        if final_results:
            logger.info(f"總共找到 {len(final_results)} 首相關歌曲。")
            return final_results, None
        else:
            logger.warning(f"所有策略都未能為 video_id: {video_id} 找到任何相關歌曲。")
            return [], "找不到相關影片"
