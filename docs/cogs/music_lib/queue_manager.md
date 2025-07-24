# Music Library - Queue Manager

**File:** [`cogs/music_lib/queue_manager.py`](cogs/music_lib/queue_manager.py)

The `QueueManager` is responsible for all logic related to the song queue. It manages the order of songs, playback modes, and shuffle settings for each server.

## `PlayMode(Enum)`

An enumeration that defines the possible playback modes:
*   `NO_LOOP`: The queue plays once.
*   `LOOP_QUEUE`: The entire queue repeats.
*   `LOOP_SINGLE`: The current song repeats.

## `QueueManager` Class

### `__init__(self, bot)`

Initializes the manager, creating dictionaries to hold the queues (`guild_queues`), settings (`guild_settings`), and playlists (`guild_playlists`) for each server.

### Key Methods

#### `get_queue(self, guild_id: int) -> asyncio.Queue`

Retrieves the `asyncio.Queue` instance for a specific guild. If one doesn't exist, it creates a new one.

#### `add_to_queue(self, guild_id, item, ...)`

Adds a song to the queue. This method contains intelligent logic for managing the queue:
*   **Priority for Users:** Songs added by users are prioritized over songs added by the bot's autoplay feature. They are inserted before the first autoplayed song in the queue.
*   **Queue Full Handling:** If the queue is full (`MAX_QUEUE_SIZE`), and a user adds a song, the manager will attempt to remove the last autoplayed song to make space. If a bot tries to add a song to a full queue, the action fails.

#### `add_to_front_of_queue(self, guild_id, item, ...)`

Adds a song to the very beginning of the queue, making it the next song to be played. This is typically used for single-song requests.

#### `get_next_item(self, guild_id: int)`

Retrieves and removes the next song from the front of the queue.

#### Play Mode & Shuffle

*   **`set_play_mode(...)` / `get_play_mode(...)`:** Sets and gets the `PlayMode` for the guild.
*   **`toggle_shuffle(...)` / `is_shuffle_enabled(...)`:** Toggles and checks the shuffle status for the guild.

#### Playlist Handling

The manager distinguishes between the active `queue` and a `playlist`. The `playlist` holds songs from a YouTube playlist that have not yet been added to the active queue.

*   **`set_playlist(self, ...)`:** Stores a list of songs from a YouTube playlist.
*   **`get_next_playlist_songs(self, ...)`:** Retrieves a specified number of songs from the stored playlist to be added to the active queue. This is typically done when the active queue is running low on songs.