# Music Library - YouTube Manager

**File:** [`cogs/music_lib/youtube.py`](cogs/music_lib/youtube.py)

The `YouTubeManager` is the sole interface for all interactions with YouTube. It handles searching for videos, downloading audio, and retrieving video metadata.

## `YouTubeManager` Class

### `__init__(self, time_limit=1800)`

Initializes the manager.

*   **Parameters:**
    *   `time_limit` (int): A limit in seconds for the duration of downloadable videos (defaults to 1800s / 30 minutes).
*   **Process:** It loads FFmpeg and `yt-dlp` configurations from the main `settings.json` file.

### `create(cls, ...)`

An asynchronous class method for creating an instance of the manager. It also performs a crucial check to ensure that FFmpeg is installed and accessible on the system.

### Key Methods

#### `async search_videos(self, query, ...)`

Searches YouTube for videos matching a given query.

*   **Process:** It uses the `youtube_search` library to perform the search and then processes the results to ensure they are in a consistent format, including converting duration strings (e.g., "3:21") into seconds.
*   **Returns:** A list of dictionaries, with each dictionary containing metadata for a video.

#### `async download_audio(self, url, folder, ...)`

Downloads the audio from a given YouTube URL and saves it as an MP3 file.

*   **Process:** This is a complex method that uses the `yt-dlp` library.
    1.  It first extracts the video's metadata without downloading to check if it's a live stream or if its duration exceeds the `time_limit`.
    2.  If it's a live stream, it returns the stream URL without downloading.
    3.  If it's a standard video, it proceeds to download the best available audio stream.
    4.  It uses FFmpeg (via `yt-dlp`'s postprocessor settings) to convert the audio to MP3.
    5.  It includes a retry mechanism for the download process.
*   **Returns:** A tuple `(video_info, error)`. `video_info` is a dictionary containing the song's metadata, including the local `file_path`. `error` is a string if the download failed.

#### `async get_video_info_without_download(self, url, ...)`

A lighter version of `download_audio` that only fetches the video's metadata without downloading the audio file. This is used when adding songs to the queue while another song is already playing to avoid unnecessary downloads.

#### `async download_playlist(self, url, folder, ...)`

Handles the downloading of an entire YouTube playlist.

*   **Process:**
    1.  It uses `yt-dlp` to extract the information for all videos in the playlist.
    2.  To provide a fast response, it immediately downloads the *first* song of the playlist.
    3.  It returns the metadata for the first song (including its `file_path`) along with a list of metadata for all *other* songs in the playlist, which will be downloaded later as they move up the queue.

#### `async get_related_videos(self, video_id, ...)`

Provides the logic for the autoplay feature. It uses a multi-layered strategy to find relevant songs:
1.  First, it tries searching for other songs by the same artist/channel.
2.  If that yields few results, it searches using a "cleaned" version of the original song's title (removing terms like "official video", "lyrics", etc.).
3.  As a final fallback, it uses `yt-dlp`'s "up next" feature to get YouTube's own recommendations.