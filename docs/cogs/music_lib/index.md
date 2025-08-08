# Music Library

**Location:** [`cogs/music_lib/`](cogs/music_lib/)

The Music Library is a collection of modules that together form the backbone of the bot's music playback feature. It is designed with a clear separation of concerns, with each manager handling a specific aspect of the music system. The main `YTMusic` cog in [`cogs/music.py`](../music.md) acts as the orchestrator for this library.

## Core Components

The library is composed of the following managers:

*   **[State Manager](./state_manager.md):** Tracks the current playback state for each server.
*   **[Queue Manager](./queue_manager.md):** Manages the song queue, playback modes, and shuffle settings.
*   **[Audio Manager](./audio_manager.md):** Handles the creation of audio sources for Discord.
*   **[YouTube Manager](./youtube.md):** Interfaces with YouTube for searching and downloading.
*   **[UI Manager](./ui_manager.md):** Creates and manages the interactive player interface.