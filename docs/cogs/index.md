# Discord Bot Cogs Documentation

This directory contains the documentation for all Discord bot cogs (extensions). Each cog is a self-contained module that provides specific functionality to the Discord bot.

## Overview

The bot consists of 17 main cog modules plus several subdirectories containing specialized functionality. Each cog is designed to be modular and can be loaded independently.

## Main Cogs

### Core System Modules
- **[botinfo.md](botinfo.md)** - Bot information display and system statistics
- **[help.md](help.md)** - Command help system with multi-language support
- **[language_manager.md](language_manager.md)** - Multi-language translation system
- **[channel_manager.md](channel_manager.md)** - Server and channel permission management

### Media & Entertainment
- **[music.md](music.md)** - YouTube music player with queue management
- **[gen_img.md](gen_img.md)** - AI-powered image generation using Gemini and local models
- **[gif_tools.md](gif_tools.md)** - GIF search and management using Tenor API
- **[summarizer.md](summarizer.md)** - AI-powered conversation summarization

### Utility & Productivity
- **[math.md](math.md)** - Mathematical calculation engine using SymPy
- **[remind.md](remind.md)** - Time-based reminder system with natural language parsing
- **[schedule.md](schedule.md)** - Personal schedule management with YAML file support
- **[internet_search.md](internet_search.md)** - Web search using Google Search API and web scraping

### Memory & Learning
- **[userdata.md](userdata.md)** - Personal user data management and preferences
- **[episodic_memory.md](episodic_memory.md)** - Episodic memory system for conversation context

### Content Management
- **[story_manager.md](story_manager.md)** - Interactive story creation and management system
- **[system_prompt_manager.md](system_prompt_manager.md)** - Dynamic system prompt management per channel/guild
- **[update_manager.md](update_manager.md)** - Automatic bot update system

## Specialized Subdirectories

### [eat/](../cogs/eat/) - Food Recommendation System
- **Purpose**: Restaurant and food recommendation with AI-powered suggestions
- **Features**: Location-based search, personal preferences learning, review analysis
- **Key Components**: Google Maps integration, ML-based recommendation engine

### [memory/](../cogs/memory/) - Memory Management System  
- **Purpose**: Advanced memory management for episodic and procedural memories
- **Features**: Vector storage, message tracking, event summarization
- **Architecture**: Modular storage interfaces, embedding providers, vector stores

### [music_lib/](../cogs/music_lib/) - Music System Library
- **Purpose**: Core music playback and queue management system
- **Components**:
  - `audio_manager.py` - Audio processing and playback
  - `queue_manager.py` - Song queue and playlist management  
  - `state_manager.py` - Player state persistence
  - `ui_manager.py` - User interface management
  - `youtube.py` - YouTube integration and audio downloading
  - `ui/` - User interface components (buttons, progress bars, song selection)

### [story/](../cogs/story/) - Story System Core
- **Purpose**: Interactive storytelling system with AI-powered narrative generation
- **Features**: Multi-character stories, world building, relationship tracking
- **Architecture**:
  - `database.py` - SQLite database for stories, characters, and relationships
  - `manager.py` - Core story processing and AI agent coordination
  - `models.py` - Data models and Pydantic schemas
  - `prompt_engine.py` - Dynamic prompt generation for AI agents
  - `state_manager.py` - Story state management
  - `ui/` - User interface components (modals, views, UI manager)

### [system_prompt/](../cogs/system_prompt/) - System Prompt Management
- **Purpose**: Dynamic system prompt management for AI conversations
- **Features**: Per-channel/guild prompts, permission-based editing, template system
- **Components**: Manager, commands, permissions, caching, validation

## Architecture Patterns

### Common Features
All cogs follow these design patterns:

1. **Multi-language Support**: All user-facing text uses the `LanguageManager` for localization
2. **Error Handling**: Consistent error reporting through `func.report_error()`
3. **Configuration**: Settings loaded from `addons/settings.py`
4. **Async/Await**: Full asynchronous operation for optimal performance
5. **Permission Checks**: Proper Discord permission validation

### Dependencies
- **Core**: `discord.py`, `asyncio`
- **AI/LLM**: `langchain`, Google Generative AI SDK
- **Database**: `sqlite3`, `sqlalchemy`
- **Media**: `PIL`, `yt-dlp`, `ffmpeg`
- **Utilities**: `aiohttp`, `python-dateutil`, `sympy`

## Usage

Each cog can be loaded independently using Discord's cog loading system:

```python
# Load a specific cog
await bot.load_extension('cogs.music')

# Unload a cog  
await bot.unload_extension('cogs.music')
```

## Configuration

Cog-specific configuration is managed through:
- `addons/settings.py` - Main configuration file
- `base_configs/` - Base configuration templates
- `data/` - Runtime data storage
- Database files - Persistent storage for user data

## Development Guidelines

When working with cogs:

1. **Follow PEP 8** style guidelines
2. **Use async/await** for all I/O operations
3. **Implement proper error handling** with `func.report_error()`
4. **Support multi-language** through `LanguageManager`
5. **Validate permissions** before executing privileged operations
6. **Use type hints** for better code documentation
7. **Write comprehensive docstrings** in English

## Command Structure

Most cogs provide both slash commands (`/command`) and support for traditional message-based commands where appropriate. Slash commands are preferred for better user experience and permission handling.

---

*This documentation is automatically generated from the source code. For detailed implementation specifics, refer to individual module documentation.*