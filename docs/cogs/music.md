# Music Cog

**File:** [`cogs/music.py`](cogs/music.py)

The `YTMusic` cog is the main interface for the bot's music playback functionality. It handles user commands, interacts with the various components of the music library, and manages the overall playback state for each server.

## Dependencies

This cog is the primary user-facing component of the **[Music Library](./music_lib/index.md)**. It integrates the following managers from the library:

*   **`YouTubeManager`:** For searching and downloading audio from YouTube.
*   **`AudioManager`:** For creating audio sources for playback.
*   **`StateManager`:** For tracking the playback state of each server.
*   **`QueueManager`:** For managing the song queue, play modes, and shuffle.
*   **`UIManager`:** For displaying and updating the music player interface.

## Commands

### `/play`

The central command for music playback.

*   **Parameters:**
    *   `query` (Optional[str]): A YouTube URL (video or playlist) or a search term.
*   **Behavior:**
    *   If a user is not in a voice channel, it returns an error.
    *   If the bot is not in a voice channel, it joins the user's channel.
    *   If `query` is provided, it searches for the song/playlist and adds it to the queue.
    *   If `query` is a search term, it presents a selection of search results.
    *   If `query` is a playlist URL, it adds the songs to the queue.
    *   If no `query` is provided, it refreshes the player UI.

### `/mode`

Sets the playback mode for the queue.

*   **Parameters:**
    *   `mode` (Choice): The desired playback mode.
        *   `不循環 (No Loop)`: The queue plays once and then stops.
        *   `清單循環 (Loop Queue)`: The entire queue repeats after the last song.
        *   `單曲循環 (Loop Single)`: The current song repeats indefinitely.

### `/shuffle`

Toggles shuffle mode for the current queue. When enabled, the queue will be randomized.

## Core Logic

### Playback Flow

1.  A user invokes the `/play` command with a query.
2.  The cog validates that the user is in a voice channel and connects if necessary.
3.  The `query` is passed to the `YouTubeManager` to either search for videos or download audio from a URL.
4.  The retrieved song information is added to the `QueueManager`.
5.  If the bot is not already playing, the `play_next` method is called.
6.  `play_next` retrieves the next song from the `QueueManager`, creates an audio source using the `AudioManager`, and starts playback.
7.  The `UIManager` is called to display or update the interactive music player, which includes buttons for play/pause, skip, stop, etc.
8.  When a song finishes, the `_handle_after_play` callback is triggered, which then calls `play_next` again to continue the cycle.

### Autoplay

The cog features an autoplay system. When the queue is about to run out of user-added songs, the `_trigger_autoplay` method uses the `YouTubeManager` to find related videos based on the last played song and adds them to the queue to keep the music going.