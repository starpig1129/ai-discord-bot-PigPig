# Discord Music Bot Module

This module provides music playback functionality for Discord servers using YouTube as the source.

## Architecture

The module is split into several components for better maintainability and separation of concerns:

### Core Components

- `player.py`: Main cog class that handles Discord commands and orchestrates other components
- `youtube.py`: Handles YouTube video searching, info fetching, and downloading
- `queue_manager.py`: Manages music queues and playlists for each guild
- `state_manager.py`: Manages player state (current song, message, etc.) for each guild
- `audio_manager.py`: Handles audio playback and file operations
- `ui_manager.py`: Manages player UI updates and message handling

### UI Components

- `ui/controls.py`: Music player control buttons
- `ui/progress.py`: Progress bar display
- `ui/song_select.py`: Song selection menu for search results

## Features

- Play music from YouTube URLs or search queries
- Support for playlists
- Queue management (up to 5 songs)
- Multiple playback modes:
  - No loop
  - Queue loop
  - Single song loop
- Shuffle mode
- Progress bar display
- Interactive controls
- Automatic cleanup of downloaded files

## Commands

- `/play <query>`: Play music from URL or search query
- `/mode <mode>`: Set playback mode (no_loop/loop_queue/loop_single)
- `/shuffle`: Toggle shuffle mode

## Implementation Details

### State Management
- Each guild has its own state managed by `StateManager`
- State includes current song, message, and view

### Queue Management
- Maximum 5 songs in queue
- Additional songs from playlists are stored separately
- Automatic queue refill from playlist

### Audio Handling
- Files are downloaded only when needed
- Automatic cleanup of old files
- Efficient audio source management

### UI Updates
- Real-time progress bar updates
- Automatic message recreation on token expiry
- Clean error handling and user feedback

## Error Handling

- Comprehensive error handling throughout
- User-friendly error messages
- Automatic recovery from common issues
- Detailed logging for troubleshooting

## Best Practices

- Modular design for easy maintenance
- Clear separation of concerns
- Efficient resource management
- Comprehensive error handling
- Detailed logging
- Clean code organization
