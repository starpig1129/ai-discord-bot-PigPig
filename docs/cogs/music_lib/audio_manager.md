# Music Library - Audio Manager

**File:** [`cogs/music_lib/audio_manager.py`](cogs/music_lib/audio_manager.py)

The `AudioManager` is a focused utility class responsible for creating audio sources that Discord can play and for managing the cleanup of temporary audio files.

## `AudioManager` Class

### `create_audio_source(self, song: Dict[str, Any]) -> FFmpegPCMAudio`

This is the primary method of the class. It takes a song dictionary and returns a `discord.FFmpegPCMAudio` object, which is the audio source that the bot's voice client plays.

*   **Parameters:**
    *   `song` (Dict[str, Any]): A dictionary containing the song's metadata.
*   **Logic:**
    *   **Live Streams:** If the song dictionary has `is_live` set to `True`, it uses the `stream_url` and applies FFmpeg options optimized for reconnecting to live streams (`-reconnect 1`, etc.).
    *   **Local Files:** If the song is not a live stream, it uses the `file_path` to create a standard audio source for a local file.
*   **Returns:** A playable `FFmpegPCMAudio` source.
*   **Raises:** `ValueError` if the required information (like `stream_url` or `file_path`) is missing from the song dictionary.

### `delete_file(self, guild_id: int, file_path: str)`

An asynchronous method for safely deleting a temporary audio file from the disk. It uses `asyncio.to_thread` to run the file deletion in a separate thread, preventing it from blocking the bot's main event loop.

### `cleanup_guild_files(self, guild_id: int, folder: str)`

A utility method to clean up all temporary audio files for a specific guild. This is typically called when the bot disconnects or the queue is stopped.