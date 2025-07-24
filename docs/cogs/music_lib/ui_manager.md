# Music Library - UI Manager

**File:** [`cogs/music_lib/ui_manager.py`](cogs/music_lib/ui_manager.py)

The `UIManager` is responsible for creating, managing, and updating the interactive music player interface that users see in Discord.

## `UIManager` Class

### `__init__(self, bot)`

Initializes the UI manager. It holds a reference to the bot to access other cogs, like the `LanguageManager`.

### `async update_player_ui(self, interaction, item, ...)`

This is the main method of the class. It is called whenever a new song starts playing or when the UI needs to be refreshed.

*   **Parameters:**
    *   `interaction`: The `discord.Interaction` that triggered the update.
    *   `item` (Dict): The song dictionary for the currently playing track.
    *   `current_message` (Optional[discord.Message]): The existing player message, if there is one.
    *   `youtube_manager`: An instance of the `YouTubeManager` to get thumbnail URLs.
    *   `music_cog`: An instance of the main `YTMusic` cog to link the button callbacks.
*   **Process:**
    1.  **Cleanup:** It first deletes all previous UI messages sent by the music system to keep the channel clean.
    2.  **Embed Creation:** It calls `_create_player_embed` to build a new, updated embed with the current song's information.
    3.  **View Creation:** It creates a new instance of `MusicControlView`, passing it a dictionary of callback functions from the main `YTMusic` cog. This links the buttons in the view to the actual logic (like skipping, stopping, etc.).
    4.  **Sending:** It sends a new message with the updated embed and view.
    5.  **State Update:** It updates the `StateManager` with the new message object.
    6.  **Progress Bar:** If the song is not a live stream, it starts the progress bar updater task on the new view.
*   **Returns:** The newly created `discord.Message` object for the player UI.

### `_create_player_embed(self, item, ...)`

A helper method that constructs the `discord.Embed` for the player. It uses the `LanguageManager` to get localized text for all field names (e.g., "Now Playing," "Duration"). It includes the song title, uploader, duration, view count, a progress bar, and the requester's information in the footer.

## UI Components

The `UIManager` uses custom `discord.ui.View` and `discord.ui.Button` classes defined in `cogs/music_lib/ui/` to create the interactive elements.

*   **`MusicControlView`:** The main view that contains all the control buttons (play/pause, skip, stop, mode, shuffle, etc.). It also manages the background task for updating the progress bar.
*   **`ProgressDisplay`:** A helper class for creating the text-based progress bar string.
*   **`SongSelectView`:** A view used specifically for search results, presenting the user with a dropdown menu to select which song they want to add to the queue.