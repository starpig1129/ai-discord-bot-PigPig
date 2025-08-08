# Music Library - State Manager

**File:** [`cogs/music_lib/state_manager.py`](cogs/music_lib/state_manager.py)

The `StateManager` is a simple yet crucial component of the music library. Its sole responsibility is to maintain the playback state for each server (guild) where the bot is active.

## `PlayerState` Data Class

This data class defines the structure for storing the state of a single server's music player. An instance of this class is created for each active guild.

*   **Attributes:**
    *   `current_song` (Optional[Dict]): A dictionary containing information about the song that is currently playing.
    *   `last_played_song` (Optional[Dict]): A dictionary containing information about the last song that finished playing. This is used for the autoplay feature.
    *   `current_message` (Optional[discord.Message]): The `discord.Message` object that displays the main player UI. This is stored so it can be updated.
    *   `current_view` (Optional[MusicControlView]): The instance of the interactive view attached to the player message.
    *   `ui_messages` (List[discord.Message]): A list of all messages sent by the music system (e.g., "Song added," "Queue finished"). This is used for cleanup.
    *   `autoplay` (bool): A flag indicating whether autoplay is enabled for the server.

## `StateManager` Class

### `__init__(self)`

Initializes the manager with an empty dictionary to hold the `PlayerState` for each guild.

### `get_state(self, guild_id: int) -> PlayerState`

This is the primary method for accessing a server's state.

*   **Behavior:** It retrieves the `PlayerState` for the given `guild_id`. If no state exists for that guild yet, it creates a new, default `PlayerState` object, adds it to the internal dictionary, and then returns it. This ensures that a state object is always available on demand.

### `update_state(self, guild_id: int, **kwargs)`

A convenience method for updating one or more attributes of a guild's `PlayerState`.

*   **Example:** `state_manager.update_state(guild_id, current_song=new_song, autoplay=True)`

### `clear_state(self, guild_id: int)`

Removes the `PlayerState` for a guild from memory. This is typically called when the bot leaves a voice channel or is stopped.