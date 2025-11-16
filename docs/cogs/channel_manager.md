# ChannelManager Cog Documentation

## Overview

The ChannelManager cog provides comprehensive server and channel permission management capabilities. It enables administrators to configure bot response modes, manage whitelists/blacklists, set channel-specific modes, and control automatic responses on a per-channel basis.

## Features

### Core Functionality
- **Server-wide Response Modes**: Unrestricted, whitelist, or blacklist modes
- **Channel-specific Modes**: Special modes like story mode for individual channels
- **Whitelist/Blacklist Management**: Fine-grained channel access control
- **Auto-response Configuration**: Enable/disable automatic bot responses per channel
- **Multi-language Support**: Fully localized administrative interface

### Key Components
- `ChannelManager` class - Main cog implementation
- JSON-based configuration storage
- Permission validation system
- Channel mode resolution logic

## Commands

### `/set_server_mode`
Sets the server-wide response mode for all channels.

**Parameters**:
- `mode`: Server response mode selection
  - `unrestricted`: Bot responds in all channels
  - `whitelist`: Bot responds only in whitelisted channels
  - `blacklist`: Bot responds in all channels except blacklisted ones

**Permissions**: Administrator only

### `/set_channel_mode`
Sets a special mode for a specific channel.

**Parameters**:
- `channel`: Target Discord text channel
- `mode`: Channel mode selection
  - `default`: Use server-wide settings
  - `story`: Enable story mode for interactive storytelling

**Permissions**: Administrator only

### `/add_channel`
Adds a channel to the whitelist or blacklist.

**Parameters**:
- `channel`: Target Discord text channel
- `list_type`: List type selection
  - `whitelist`: Add to allowed channels list
  - `blacklist`: Add to blocked channels list

**Permissions**: Administrator only

### `/remove_channel`
Removes a channel from the whitelist or blacklist.

**Parameters**:
- `channel`: Target Discord text channel
- `list_type`: List type selection
  - `whitelist`: Remove from allowed channels list
  - `blacklist`: Remove from blocked channels list

**Permissions**: Administrator only

### `/auto_response`
Enables or disables automatic bot responses for a specific channel.

**Parameters**:
- `channel`: Target Discord text channel
- `enabled`: Boolean to enable/disable auto-response

**Permissions**: Administrator only

## Technical Implementation

### Class Structure
```python
class ChannelManager(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    def get_config_path(self, guild_id) -> str
    def load_config(self, guild_id) -> dict
    def save_config(self, guild_id, config)
    async def check_admin_permissions(self, interaction: discord.Interaction) -> bool
    
    # Command handlers
    async def set_server_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str])
    async def set_channel_mode(self, interaction: discord.Interaction, channel: discord.TextChannel, mode: app_commands.Choice[str])
    async def add_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel, list_type: app_commands.Choice[str])
    async def remove_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel, list_type: app_commands.Choice[str])
    async def auto_response_command(self, interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool)
```

### Configuration System

#### Data Structure
```json
{
  "mode": "unrestricted",  // Server-wide mode
  "whitelist": [],         // Array of channel IDs
  "blacklist": [],         // Array of channel IDs
  "auto_response": {},     // Channel ID -> boolean mapping
  "channel_modes": {}      // Channel ID -> mode string mapping
}
```

#### Configuration Management
- **Storage Location**: `data/channel_configs/{guild_id}.json`
- **File Format**: JSON with UTF-8 encoding
- **Atomic Updates**: Safe file writing with error handling
- **Default Config**: Automatic creation for new servers

### Permission System

#### Administrator Validation
```python
async def check_admin_permissions(self, interaction: discord.Interaction) -> bool:
    bot_owner_id = getattr(self.tokens, 'bot_owner_id', 0)
    if interaction.user.guild_permissions.administrator or interaction.user.id == bot_owner_id:
        return True
    
    # Send localized permission denied message
    error_message = self.lang_manager.translate(...)
    await interaction.response.send_message(error_message, ephemeral=True)
    return False
```

#### Bot Owner Override
- Bot owner has full administrative access regardless of server permissions
- Configurable through `addons.tokens.bot_owner_id`
- Provides emergency access for maintenance

### Channel Resolution Logic

#### Mode Evaluation Flow
```python
def is_allowed_channel(self, channel: discord.TextChannel, guild_id: str) -> Tuple[bool, bool, Optional[str]]:
    config = self.load_config(guild_id)
    channel_id = str(channel.id)
    auto_response_enabled = config.get("auto_response", {}).get(channel_id, False)

    # 1. Check channel-specific mode override
    channel_mode = config.get("channel_modes", {}).get(channel_id)
    if channel_mode:  # e.g., 'story'
        return True, auto_response_enabled, channel_mode

    # 2. Use server-wide mode
    server_mode = config.get("mode", "unrestricted")
    if server_mode == "unrestricted":
        return True, auto_response_enabled, server_mode
    elif server_mode == "whitelist":
        is_allowed = channel_id in config.get("whitelist", [])
        return is_allowed, auto_response_enabled, server_mode
    elif server_mode == "blacklist":
        is_allowed = channel_id not in config.get("blacklist", [])
        return is_allowed, auto_response_enabled, server_mode
        
    return False, False, server_mode
```

#### Priority Order
1. **Channel-specific modes** (highest priority)
2. **Server-wide unrestricted mode**
3. **Server-wide whitelist mode**
4. **Server-wide blacklist mode**
5. **Default deny** (lowest priority)

### Data Migration and Validation

#### Configuration Sanitization
```python
def _sanitize_schedule_data(self, data, fallback_channel_id: int):
    """Ensure config has required keys and proper types"""
    repaired = False
    
    if not isinstance(data, dict):
        data = {}
        repaired = True
        
    if 'mode' not in data:
        data['mode'] = "unrestricted"
        repaired = True
        
    # Ensure arrays exist
    for key in ['whitelist', 'blacklist']:
        if key not in data or not isinstance(data[key], list):
            data[key] = []
            repaired = True
            
    # Ensure dictionaries exist
    for key in ['auto_response', 'channel_modes']:
        if key not in data or not isinstance(data[key], dict):
            data[key] = {}
            repaired = True
    
    return data, repaired
```

## Configuration Management

### File Operations
- **Atomic Writes**: Temporary file + rename for safety
- **Error Handling**: Graceful handling of file system errors
- **UTF-8 Encoding**: Proper text encoding for internationalization
- **Backup Creation**: Optional backup of existing configurations

### Server Onboarding
- **Automatic Defaults**: New servers get default configuration
- **Migration Support**: Automatic upgrade of old configuration formats
- **Validation**: Configuration integrity checking

## Error Handling

### Robust Error Recovery
- **JSON Parsing Errors**: Fallback to default configuration
- **File System Issues**: Graceful handling of disk problems
- **Permission Errors**: User-friendly permission denial messages
- **Network Issues**: Localized error message delivery

### Validation System
- **Input Validation**: Sanitize all user inputs
- **Type Checking**: Ensure proper data types in configuration
- **Range Validation**: Validate channel IDs and boolean values

## Performance Considerations

### Efficient Configuration Loading
- **Cached Configurations**: In-memory caching of server configs
- **Lazy Loading**: Load config only when needed
- **Minimal I/O**: Read/write operations minimized

### Memory Management
- **Config Caching**: Cache configurations in memory
- **Automatic Cleanup**: Remove cached configs for departed servers
- **Memory Limits**: Prevent excessive memory usage

## Security & Permissions

### Access Control Matrix
| Action | Required Permission | Bot Owner Override |
|--------|-------------------|-------------------|
| Set server mode | Administrator | Yes |
| Set channel mode | Administrator | Yes |
| Add/remove from lists | Administrator | Yes |
| Configure auto-response | Administrator | Yes |
| View current settings | Read Messages | Yes |

### Data Protection
- **Server Isolation**: Configurations separated by server ID
- **Secure File Storage**: Proper file permissions
- **Input Sanitization**: Protection against injection attacks

## Integration Points

### With Other Cogs
```python
# ChannelManager provides access control for other features
from cogs.channel_manager import ChannelManager

# Check if bot can respond in channel
channel_manager = bot.get_cog("ChannelManager")
allowed, auto_response, mode = channel_manager.is_allowed_channel(channel, guild_id)
```

### Usage Patterns
- **Story Mode**: Story manager checks for story mode channel setting
- **Auto-response**: AI responses respect auto-response configuration
- **Permission System**: Centralized permission checking for all features

## Usage Examples

### Basic Server Configuration
```
Admin: /set_server_mode whitelist
Bot: Server response mode set to: Whitelist

Admin: /add_channel #general whitelist
Bot: Channel #general added to whitelist
```

### Channel-specific Modes
```
Admin: /set_channel_mode #story-room story
Bot: Channel #story-room mode set to: Story mode
```

### Auto-response Control
```
Admin: /auto_response #support-channel enabled
Bot: Channel #support-channel auto-response set to: True
```

## Related Files

- `cogs/channel_manager.py` - Main implementation
- `data/channel_configs/` - Configuration storage directory
- `LanguageManager` - Translation system
- `addons.tokens` - Bot owner configuration

## Future Enhancements

Potential improvements:
- Configuration import/export
- Bulk channel operations
- Advanced permission roles
- Configuration templates
- Audit logging
- Web-based configuration interface