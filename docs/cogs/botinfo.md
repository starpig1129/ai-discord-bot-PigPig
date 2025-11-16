# BotInfo Cog Documentation

## Overview

The BotInfo cog provides comprehensive bot information display and system monitoring capabilities. It offers both basic statistics and performance metrics through Discord embeds.

## Features

### Core Functionality
- **Bot Statistics Display**: Server count, user count, channel statistics
- **Performance Monitoring**: Network latency, memory usage, uptime tracking
- **System Information**: Bot status, loaded cogs, command counts
- **Multi-language Support**: All text localized through LanguageManager

### Key Components
- `BotInfo` class - Main cog implementation
- `botinfo` slash command - Primary user interface
- Uptime calculation and formatting
- Memory usage monitoring
- System resource tracking

## Commands

### `/botinfo`
Displays comprehensive bot information including:
- **Basic Statistics**: Server count, user count, text/voice channels
- **Performance Metrics**: Network latency, memory usage, uptime
- **System Status**: Bot status, loaded cogs, command counts

**Parameters**: None

**Response**: Rich embed with multiple sections of bot information

## Technical Implementation

### Class Structure
```python
class BotInfo(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    def _format_uptime(self, uptime) -> str
    async def botinfo(self, interaction: discord.Interaction)
```

### Key Methods

#### `_format_uptime(uptime)`
Formats uptime duration into human-readable Chinese text:
- Converts timedelta to days, hours, minutes, seconds
- Handles singular/plural forms appropriately
- Returns formatted string for display

#### `botinfo()` Command Handler
Main command implementation:
1. Calculates bot uptime
2. Measures network latency  
3. Monitors memory usage
4. Gathers statistics from bot
5. Creates formatted embed
6. Sends to user

### Configuration

#### Dependencies
- `discord.py` - Discord API wrapper
- `LanguageManager` - Multi-language support
- `func` - Error reporting utility

#### Data Sources
- Bot guilds collection
- Bot cogs collection  
- System memory via `resource` module
- Network latency measurement

## Error Handling

### Robust Fallback System
- Graceful handling when LanguageManager unavailable
- Safe attribute access with `getattr()`
- Default values for missing data
- Error reporting through `func.report_error()`

### Memory Safety
- Exception handling for memory measurement
- Platform-specific memory calculation
- Fallback values for unsupported systems

## Display Format

### Embed Structure
```yaml
Title: Bot Information Overview
Color: Discord Blue (114, 137, 218)
Thumbnail: Bot avatar
Author: Bot name and discriminator

Fields:
  - Basic Statistics
  - Performance Monitoring  
  - Feature Modules
Footer: Status indicator with bot avatar
```

### Localized Text
All user-facing text supports multiple languages:
- Traditional Chinese (zh_TW) - Default
- Simplified Chinese (zh_CN)
- English (en_US)
- Japanese (ja_JP)

### Status Indicators
- Online: Green indicator
- Idle: Yellow indicator  
- DND: Red indicator
- Offline: Gray indicator
- Unknown: Fallback status

## Performance Considerations

### Efficient Statistics Gathering
- Minimal API calls to gather statistics
- Cached bot state where possible
- Async operations for non-blocking execution

### Memory Monitoring
- Platform-aware memory calculation
- Linux/Windows specific implementations
- Resource module utilization

## Security & Permissions

### Access Control
- Public command - no special permissions required
- Safe information disclosure only
- No sensitive system data exposed

## Usage Examples

### Basic Usage
```
User: /botinfo
Bot: [Rich embed with bot statistics and performance data]
```

### Expected Output
- Server count and user statistics
- Memory usage and network latency
- Uptime in human-readable format
- Loaded cogs and command counts
- System status indicator

## Related Files

- `cogs/botinfo.py` - Main implementation
- `LanguageManager` - Localization system
- `func.report_error()` - Error handling
- Translation files - User interface text

## Future Enhancements

Potential improvements:
- Historical performance graphs
- More detailed system metrics
- Custom status message support
- Export statistics functionality
- Dashboard integration