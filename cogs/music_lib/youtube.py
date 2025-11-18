import os
import subprocess
import asyncio
import yt_dlp
import discord
import random
import re
from youtube_search import YoutubeSearch
from addons.settings import music_config
from addons.logging import get_logger

log = get_logger(source=__name__, server_id="system")

async def check_ffmpeg(ffmpeg_path='/usr/bin/ffmpeg'):
    try:
        await asyncio.to_thread(
            lambda: subprocess.run([ffmpeg_path, '-version'], capture_output=True, check=True)
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        log.error(f"FFmpeg 無法使用或運作異常: {ffmpeg_path}")
        return False

class YouTubeManager:
    def __init__(self, time_limit=1800):
        self.time_limit = time_limit
        try:
            self.settings = music_config
            self.ffmpeg_config = self.settings.ffmpeg
        except Exception as e:
            log.error(f"載入 FFmpeg 設定失敗，使用預設值: {e}")
            self.ffmpeg_config = self._get_default_ffmpeg_config()
    
    def _get_default_ffmpeg_config(self) -> dict:
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
        args = []
        pp_config = self.ffmpeg_config.get("postprocessor_args", {})
        
        args.extend([
            "-threads", str(pp_config.get("threads", 2)),
            "-loglevel", pp_config.get("loglevel", "warning"),
            "-y",
            "-q:a", "2",
            "-ar", "44100",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "30",
            "-timeout", "30000000",
            "-max_muxing_queue_size", "2048",
            "-analyzeduration", "20M",
            "-probesize", "20M"
        ])
        
        for key, value in pp_config.items():
            if key in ["threads", "loglevel", "overwrite_output", "reconnect", "reconnect_streamed", 
                      "reconnect_delay_max", "timeout", "max_muxing_queue_size", "analyzeduration", "probesize"]:
                continue
                
            if isinstance(value, bool):
                if value:
                    args.extend([f"-{key}", "1"])
            else:
                args.extend([f"-{key}", str(value)])
        
        return args
        
    @classmethod
    async def create(cls, time_limit=1800):
        manager = cls(time_limit)
        ffmpeg_path = manager.ffmpeg_config.get('location', '/usr/bin/ffmpeg')
        if not await check_ffmpeg(ffmpeg_path):
            raise RuntimeError(f"系統需要 FFmpeg，但目前無法使用: {ffmpeg_path}")
        return manager

    async def search_videos(self, query, max_results=10):
        try:
            results = await asyncio.to_thread(
                lambda: YoutubeSearch(query, max_results=max_results).to_dict()
            )
            
            for result in results:
                result['url'] = f"https://youtube.com/watch?v={result['id']}"
                result['video_id'] = result['id']
                result['author'] = result.get('channel', '未知上傳者')
                result['views'] = result.get('views', '0')
                
                if 'duration' in result:
                    try:
                        if isinstance(result['duration'], int):
                            pass
                        elif isinstance(result['duration'], str):
                            parts = result['duration'].split(':')
                            if len(parts) == 2:
                                result['duration'] = int(parts[0]) * 60 + int(parts[1])
                            elif len(parts) == 3:
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
            log.error(f"YouTube 搜尋失敗: {e}")
            return []

    async def download_playlist(self, url, folder, interaction):
        try:
            await asyncio.to_thread(os.makedirs, folder, exist_ok=True)
            output_template = os.path.join(folder, '%(id)s.mp3')
            
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.ffmpeg_config.get('audio_codec', 'mp3'),
                    'preferredquality': self.ffmpeg_config.get('audio_quality', '192'),
                }],
                'outtmpl': output_template,
                'noplaylist': False,
                'extract_flat': True,
                'quiet': True,
                'no_warnings': True,
                'force_generic_extractor': False,
                'ffmpeg_location': self.ffmpeg_config.get('location', '/usr/bin/ffmpeg')
            }

            cookies_path = self.settings.youtube_cookies_path
            if os.path.exists(cookies_path):
                log.info(f"使用 Cookies 檔案: {cookies_path}")
                ydl_opts['cookiefile'] = cookies_path

            async def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            info_dict = await extract_info()
            if 'entries' not in info_dict:
                log.error("[音樂] 無法取得播放清單資訊")
                return None, "無法取得播放清單資訊"

            video_infos = []
            remaining_infos = []
            
            if info_dict['entries']:
                first_entry = info_dict['entries'][0]
                video_url = first_entry['url']
                
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
                        "file_path": None,
                        "is_live": entry.get('is_live', False)
                    }
                    for entry in info_dict['entries'][1:]
                ]
                
                first_song_download = self.download_audio(video_url, folder, interaction)
                first_song_info, error = await first_song_download
                
                if first_song_info:
                    video_infos.append(first_song_info)
                remaining_infos.extend(other_songs_info)

            video_infos.extend(remaining_infos)
            return video_infos, None

        except Exception as e:
            log.error(f"[音樂] 播放清單下載失敗: {e}")
            return None, "播放清單下載失敗"

    async def get_video_info_without_download(self, url, interaction):
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

            cookies_path = self.settings.youtube_cookies_path
            if os.path.exists(cookies_path):
                log.info(f"使用 Cookies 檔案: {cookies_path}")
                ydl_opts['cookiefile'] = cookies_path

            async def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            info_dict = await extract_info()
            is_live = info_dict.get('is_live', False)

            if not is_live and info_dict.get('duration', 0) > self.time_limit:
                log.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, 影片時長過長！")
                return None, "影片時長過長！超過 30 分鐘"

            video_info = {
                "file_path": None,
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
            log.error(f"[音樂] 取得影片資訊失敗: {e}")
            return None, "取得影片資訊失敗"

    async def download_audio(self, url, folder, interaction):
        try:
            await asyncio.to_thread(os.makedirs, folder, exist_ok=True)
            output_template = os.path.join(folder, '%(id)s')
            
            if not await asyncio.to_thread(os.access, folder, os.W_OK):
                log.error(f"無法寫入下載目錄: {folder}")
                return None, "無法寫入下載目錄"

            try:
                statvfs = await asyncio.to_thread(os.statvfs, folder)
                available_space = statvfs.f_frsize * statvfs.f_bavail
                if available_space < 100 * 1024 * 1024:
                    log.error(f"磁碟空間不足: {folder}")
                    return None, "磁碟空間不足"
            except Exception as e:
                log.error(f"檢查磁碟空間失敗: {e}")
                
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
                'progress_hooks': [lambda d: log.debug(f"下載進度: {d.get('status', 'unknown')} - {d.get('_percent_str', '0%')}")],
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
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_music', 'android', 'ios', 'web'],
                        'player_skip': ['webpage'],
                    }
                },
                'hls_prefer_native': True,
                'external_downloader_args': {
                    'ffmpeg': self._build_postprocessor_args()
                }
            }

            cookies_path = self.settings.youtube_cookies_path
            if os.path.exists(cookies_path):
                log.info(f"使用 Cookies 檔案: {cookies_path}")
                ydl_opts['cookiefile'] = cookies_path

            log.info(f"[音樂] 開始下載 (伺服器 ID: {interaction.guild.id}): {url} 到 {folder}")

            async def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            info_dict = await extract_info()
            is_live = info_dict.get('is_live', False)

            if is_live:
                log.info(f"[音樂] 偵測到直播影片 (伺服器 ID: {interaction.guild.id}): {url}")
                
                best_audio_url = None
                if 'formats' in info_dict:
                    audio_formats = [f for f in info_dict['formats'] 
                                   if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                    if audio_formats:
                        best_audio = max(audio_formats, key=lambda x: x.get('abr', 0))
                        best_audio_url = best_audio.get('url')
                    else:
                        video_formats = [f for f in info_dict['formats'] 
                                       if f.get('url') and f.get('acodec') != 'none']
                        if video_formats:
                            best_format = min(video_formats, key=lambda x: x.get('height', 9999))
                            best_audio_url = best_format.get('url')
                
                video_info = {
                    "file_path": None,
                    "title": info_dict.get('title', '未知標題'),
                    "url": info_dict.get('webpage_url', url),
                    "stream_url": best_audio_url or info_dict.get('url'),
                    "duration": 0,
                    "video_id": info_dict.get('id', '未知ID'),
                    "author": info_dict.get('uploader', '未知上傳者'),
                    "views": info_dict.get('view_count', 0),
                    "requester": interaction.user,
                    "user_avatar": interaction.user.avatar.url,
                    "is_live": True
                }
                return video_info, None

            if info_dict.get('duration', 0) > self.time_limit:
                log.info(f"[音樂] 伺服器 ID: {interaction.guild.id}, 影片時長過長！")
                return None, "影片時長過長！超過 30 分鐘"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    log.info(f"[音樂] 正在開始下載 (伺服器 ID: {interaction.guild.id}): {url}")
                    
                    max_retries = 3
                    retry_count = 0
                    last_error = None
                    
                    while retry_count < max_retries:
                        try:
                            await asyncio.to_thread(ydl.download, [url])
                            log.info(f"[音樂] 下載完成 (伺服器 ID: {interaction.guild.id}): {url}")
                            break
                        except yt_dlp.utils.DownloadError as e:
                            error_msg = str(e).lower()
                            
                            if 'signature' in error_msg or '403' in error_msg:
                                log.warning(f"[音樂] 簽名提取失敗，嘗試使用 Android 客戶端...")
                                ydl_opts['extractor_args'] = {
                                    'youtube': {'player_client': ['android_music']}
                                }
                                retry_count += 1
                                await asyncio.sleep(2)
                                continue
                            
                            elif 'timeout' in error_msg or 'connection' in error_msg:
                                retry_count += 1
                                if retry_count >= max_retries:
                                    return None, "網絡連接超時，請稍後再試"
                                log.warning(f"[音樂] 網絡錯誤，重試 {retry_count}/{max_retries}")
                                await asyncio.sleep(5)
                                continue
                            
                            elif 'not available' in error_msg or 'blocked' in error_msg:
                                return None, "此影片在您的地區不可用"
                            
                            else:
                                last_error = e
                                retry_count += 1
                                if retry_count >= max_retries:
                                    raise last_error
                                await asyncio.sleep(2)
                                
                        except Exception as e:
                            last_error = e
                            retry_count += 1
                            if retry_count >= max_retries:
                                raise last_error
                            log.warning(f"[音樂] 下載失敗，重試 {retry_count}/{max_retries}: {str(e)}")
                            await asyncio.sleep(2)
                    
                    file_path = os.path.join(folder, f"{info_dict['id']}.mp3")
                    exists = await asyncio.to_thread(os.path.exists, file_path)
                    if not exists:
                        raise Exception("輸出檔案不存在")
                    
                    size = await asyncio.to_thread(os.path.getsize, file_path)
                    if size == 0:
                        raise Exception("輸出檔案為空")

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

                    video_info = {
                        "file_path": file_path,
                        "title": info_dict.get('title', '未知標題'),
                        "url": info_dict.get('webpage_url', url),
                        "stream_url": None,
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
                    log.error(f"[音樂] 下載過程發生錯誤: {str(e)}")
                    try:
                        partial_file = os.path.join(folder, f"{info_dict['id']}")
                        
                        async def clean_file(path):
                            if await asyncio.to_thread(os.path.exists, path):
                                await asyncio.to_thread(os.remove, path)
                        
                        await asyncio.gather(
                            clean_file(partial_file),
                            clean_file(f"{partial_file}.mp3")
                        )
                    except Exception as cleanup_error:
                        log.error(f"[音樂] 無法清理部分下載檔案: {str(cleanup_error)}")
                    raise

        except yt_dlp.utils.DownloadError as e:
            log.error(f"[音樂] yt-dlp 下載錯誤: {e}")
            return None, f"下載失敗: {str(e)}"
        except Exception as e:
            log.error(f"[音樂] 下載失敗: {e}")
            return None, "下載失敗，請稍後再試"

    def get_thumbnail_url(self, video_id):
        return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

    async def get_related_videos(self, video_id: str, title: str, author: str, interaction: discord.Interaction, limit: int = 5, exclude_ids: set = None):
        if exclude_ids is None:
            exclude_ids = set()
        
        final_results = []
        exclude_ids.add(video_id)

        def process_search_results(results):
            processed = []
            for video in results:
                video_id_res = video.get('video_id')
                duration = video.get('duration', 0)
                if (video_id_res and 
                    video_id_res not in exclude_ids and 
                    not video.get('is_live', False) and
                    30 <= duration <= self.time_limit):
                    
                    processed.append({
                        "file_path": None,
                        "title": video.get('title', '未知標題'),
                        "url": video.get('url'),
                        "stream_url": None,
                        "duration": duration,
                        "video_id": video_id_res,
                        "author": video.get('author', '未知上傳者'),
                        "views": video.get('views', 0),
                        "requester": interaction.user,
                        "user_avatar": interaction.user.avatar.url,
                        "is_live": False
                    })
                    exclude_ids.add(video_id_res)
            return processed

        if author and author != '未知上傳者':
            log.info(f"策略一: 搜尋藝人 '{author}' 的歌曲...")
            try:
                clean_author = re.sub(r'\s*-\s*(topic|vevo|official).*$', '', author, flags=re.IGNORECASE).strip()
                
                queries = [
                    f"{clean_author} popular songs",
                    f"{clean_author} best songs",
                    f"{clean_author} music"
                ]
                
                author_results = []
                for query in queries:
                    if len(author_results) >= limit * 2:
                        break
                    results = await self.search_videos(query, max_results=15)
                    author_results.extend(process_search_results(results))
                
                if author_results:
                    author_results.sort(key=lambda x: x.get('views', 0), reverse=True)
                    num_to_add = min(limit - len(final_results), len(author_results))
                    
                    top_half = author_results[:num_to_add // 2]
                    random_half = random.sample(author_results[num_to_add // 2:], 
                                              min(num_to_add - len(top_half), 
                                                  len(author_results) - num_to_add // 2))
                    final_results.extend(top_half + random_half)
                    log.info(f"策略一找到 {len(final_results)} 首歌曲")

            except Exception as e:
                log.error(f"策略一失敗: {e}")

        if len(final_results) < limit:
            log.info("策略二: 使用標題關鍵字搜尋...")
            try:
                clean_title = re.sub(r'\s*[\(\[].*?(official|video|lyric|mv|audio|4k|hd|music|visualizer).*?[\)\]]', 
                                   '', title, flags=re.IGNORECASE).strip()
                
                keywords = re.sub(r'[^\w\s]', ' ', clean_title).split()
                keywords = [k for k in keywords if len(k) > 2][:3]
                
                if keywords:
                    search_query = ' '.join(keywords)
                    log.info(f"使用關鍵字搜尋: '{search_query}'")
                    
                    results = await self.search_videos(search_query, max_results=15)
                    title_results = process_search_results(results)

                    if title_results:
                        num_to_add = min(limit - len(final_results), len(title_results))
                        final_results.extend(random.sample(title_results, num_to_add))
                        log.info(f"策略二新增 {num_to_add} 首歌曲")

            except Exception as e:
                log.error(f"策略二失敗: {e}")

        if len(final_results) < limit:
            log.info("策略三: 使用 YouTube 推薦...")
            try:
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android'],
                        }
                    }
                }
                
                cookies_path = self.settings.youtube_cookies_path
                if os.path.exists(cookies_path):
                    ydl_opts['cookiefile'] = cookies_path
                
                url = f"https://www.youtube.com/watch?v={video_id}"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                    
                    if 'entries' in info and info['entries']:
                        yt_dlp_results = []
                        for entry in info['entries'][:20]:
                            entry_id = entry.get('id')
                            duration = entry.get('duration', 0)
                            
                            if (entry_id and 
                                entry_id not in exclude_ids and 
                                not entry.get('is_live') and 
                                30 <= duration <= self.time_limit):
                                
                                yt_dlp_results.append({
                                    "file_path": None,
                                    "title": entry.get('title', '未知標題'),
                                    "url": f"https://www.youtube.com/watch?v={entry_id}",
                                    "stream_url": None,
                                    "duration": duration,
                                    "video_id": entry_id,
                                    "author": entry.get('uploader', '未知上傳者'),
                                    "views": entry.get('view_count', 0),
                                    "requester": interaction.user,
                                    "user_avatar": interaction.user.avatar.url,
                                    "is_live": False
                                })
                                exclude_ids.add(entry_id)
                        
                        num_to_add = min(limit - len(final_results), len(yt_dlp_results))
                        if num_to_add > 0:
                            final_results.extend(random.sample(yt_dlp_results, num_to_add))
                            log.info(f"策略三新增 {num_to_add} 首歌曲")
            
            except Exception as e:
                log.error(f"策略三失敗: {e}")

        if final_results:
            log.info(f"總共找到 {len(final_results)} 首相關歌曲")
            return final_results, None
        else:
            log.warning(f"未找到任何相關歌曲 (video_id: {video_id})")
            return [], "找不到相關影片"
