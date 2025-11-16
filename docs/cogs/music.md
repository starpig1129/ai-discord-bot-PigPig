# Music Cog Documentation

## Overview

The Music cog provides a comprehensive YouTube music player system with advanced queue management, playback controls, autoplay functionality, and an intuitive user interface. It features a robust architecture with separated concerns across multiple library modules.

## Features

### Core Functionality
- **YouTube Integration**: Audio downloading and streaming from YouTube
- **Advanced Queue Management**: Priority queuing, shuffle, repeat modes
- **Playback Controls**: Play, pause, skip, stop, volume control
- **Autoplay System**: AI-powered song recommendations based on listening history
- **Interactive UI**: Rich embeds with progress bars and control buttons
- **Multi-language Support**: Fully localized user interface

### Key Components
- `YTMusic` class - Main cog implementation
- `YouTubeManager` - YouTube API integration and audio processing
- `AudioManager` - Audio source creation and management
- `QueueManager` - Song queuing and playlist management
- `StateManager` - Player state persistence
- `UIManager` - User interface creation and updates

## Commands

### `/play`
Plays music from YouTube by URL, search query, or refreshes the UI.

**Parameters**:
- `query`: YouTube URL, search keywords, or leave empty to refresh UI

**Requirements**: User must be in a voice channel

**Behavior**:
- **URL Input**: Downloads and plays video immediately
- **Search Input**: Shows song selection interface
- **No Input**: Refreshes current player UI

### `/mode`
Sets the playback mode for the queue.

**Parameters**:
- `mode`: Playback mode selection
  - `no_loop`: No repetition
  - `loop_queue`: Repeat entire queue
  - `loop_single`: Repeat current song

### `/shuffle`
Toggles random playback mode for the queue.

**Parameters**: None

**Effect**: Randomizes song order when enabled

## Technical Implementation

### System Architecture

#### Core Modules
```python
# Main cog
class YTMusic(commands.Cog):
    # Voice channel management
    # Command handling
    # UI interaction
    
# Library modules
from .music_lib.youtube import YouTubeManager
from .music_lib.audio_manager import AudioManager
from .music_lib.state_manager import StateManager
from .music_lib.queue_manager import QueueManager, PlayMode
from .music_lib.ui_manager import UIManager
```

#### State Management
```python
@dataclass
class PlayerState:
    current_song: Optional[dict] = None
    current_message: Optional[discord.Message] = None
    last_played_song: Optional[dict] = None
    autoplay: bool = False
    ui_messages: List[discord.Message] = field(default_factory=list)
```

### Playback Flow

#### Song Addition Process
1. **URL Detection**: Identify if input is YouTube URL or search query
2. **Audio Download**: Download audio using yt-dlp with FFmpeg processing
3. **Queue Management**: Add to appropriate queue position
4. **UI Update**: Refresh player interface
5. **Auto-play Trigger**: Start playback if nothing playing

#### Playback Control Flow
1. **Audio Source Creation**: Convert downloaded audio to Discord-compatible format
2. **Voice Client Management**: Control Discord voice connection
3. **Progress Tracking**: Monitor playback progress and update UI
4. **End-of-Song Handling**: Queue next song or trigger autoplay

### Queue Management System

#### Queue Types
- **Immediate Queue**: Songs playing now and next
- **Playlist Queue**: Additional songs from playlists
- **Autoplay Queue**: AI-recommended songs

#### Play Modes
```python
class PlayMode(Enum):
    NO_LOOP = "no_loop"
    LOOP_QUEUE = "loop_queue" 
    LOOP_SINGLE = "loop_single"
```

#### Queue Operations
- **add_to_queue()**: Add songs to end of queue
- **add_to_front_of_queue()**: Priority insertion
- **get_next_item()**: Retrieve next song
- **copy_queue()**: Create queue copy for shuffling
- **enforce_autoplay_limit()**: Manage autoplay queue size

### Autoplay System

#### Recommendation Logic
1. **Source Song Analysis**: Current or last played song
2. **Related Content Fetch**: YouTube's suggested videos
3. **Duplicate Prevention**: Filter out already queued songs
4. **Queue Management**: Add recommended songs to autoplay queue
5. **Limit Enforcement**: Maintain maximum autoplay queue size

#### Implementation Details
```python
async def _trigger_autoplay(self, interaction: discord.Interaction, guild_id: int):
    # Analyze current/last song
    song_to_recommend_from = state.current_song or state.last_played_song
    
    # Get related videos
    related_videos = await self.youtube.get_related_videos(
        video_id, title, author, interaction, limit=needed, exclude_ids=exclude_ids
    )
    
    # Add to queue with bot as source
    for video in related_videos:
        video['added_by'] = self.bot.user.id
        await self.queue_manager.add_to_queue(guild_id, video)
```

### User Interface System

#### Interactive Controls
- **Play/Pause Button**: Toggle playback state
- **Skip Button**: Skip to next song
- **Previous Button**: Return to previous song
- **Stop Button**: Stop playback and disconnect
- **Mode Button**: Cycle through play modes
- **Shuffle Button**: Toggle shuffle state
- **Queue Button**: Display current queue
- **Autoplay Button**: Toggle autoplay mode

#### UI Update Process
1. **State Collection**: Gather current playback state
2. **Embed Creation**: Generate rich embed with song info
3. **Button Configuration**: Set button states based on playback state
4. **Progress Display**: Show playback progress bar
5. **Queue Display**: List upcoming songs

### Voice Channel Management

#### Auto-Disconnect System
- **Idle Detection**: 5-minute timeout when paused
- **Channel Monitoring**: Track user presence in voice channel
- **Auto-Pause**: Pause when channel becomes empty
- **Auto-Resume**: Resume when users return

#### Implementation
```python
async def on_voice_state_update(self, member, before, after):
    # Monitor voice channel changes
    # Auto-pause when empty
    # Start disconnect timer
    # Auto-resume when users return
```

## Configuration

### Settings Location
- **Audio Processing**: `addons.settings.music_config`
- **Download Limits**: Time limits and file size restrictions
- **Queue Sizes**: Maximum queue lengths and autoplay limits

### Dependencies
- **yt-dlp**: YouTube video downloading
- **FFmpeg**: Audio conversion and processing
- **discord.py**: Discord voice and UI components

## Error Handling

### Robust Error Recovery
- **Download Failures**: Graceful handling of unavailable videos
- **Voice Connection Issues**: Automatic reconnection attempts
- **API Rate Limiting**: Throttled requests and exponential backoff
- **File Cleanup**: Automatic deletion of temporary files

### User-Friendly Errors
- **Translation Support**: All error messages localized
- **Detailed Feedback**: Specific error reasons provided
- **Recovery Suggestions**: Guidance for resolving issues

## Performance Considerations

### Audio Processing
- **FFmpeg Optimization**: Configurable audio quality settings
- **Concurrent Downloads**: Thread pool for audio processing
- **Memory Management**: Efficient audio source handling
- **File Cleanup**: Automatic temporary file deletion

### Network Optimization
- **Streaming**: Direct audio streaming without local storage when possible
- **Caching**: Intelligent caching of frequently accessed content
- **Bandwidth Management**: Configurable quality settings

## Security & Permissions

### Access Control
- **Voice Channel Required**: Users must be in voice channel to use commands
- **Administrator Bypass**: Server admins can configure permissions
- **Rate Limiting**: Prevention of spam and abuse

### Content Safety
- **URL Validation**: Safe handling of YouTube URLs
- **Content Filtering**: Respect for platform content policies
- **User Privacy**: No storage of personal listening data

## Usage Examples

### Basic Playback
```
User: /play https://www.youtube.com/watch?v=example
Bot: Downloads and starts playing the video

User: /play lofi study music  
Bot: Shows search results for user selection
```

### Queue Management
```
User: /play [multiple songs]
User: /mode loop_queue
User: /shuffle
Bot: Queue builds up, plays in shuffle mode, loops queue
```

### Interactive Controls
```
User: [Uses player buttons]
Bot: Responds to button interactions, updates UI in real-time
```

## Related Files

- `cogs/music.py` - Main cog implementation
- `cogs/music_lib/` - Library modules
  - `youtube.py` - YouTube integration
  - `audio_manager.py` - Audio processing
  - `queue_manager.py` - Queue management
  - `state_manager.py` - State persistence
  - `ui_manager.py` - UI management
  - `ui/` - UI components

## Future Enhancements

Potential improvements:
- Spotify integration
- Playlist import/export
- Voice command controls
- Advanced audio effects
- Music recognition (Shazam-style)
- Social features (shared playlists)
- Audio visualization