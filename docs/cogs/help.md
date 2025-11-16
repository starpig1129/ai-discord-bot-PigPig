# Help Cog Documentation

## Overview

The Help cog provides a comprehensive command help system with multi-language support. It dynamically generates help content by inspecting all loaded cogs and their available commands.

## Features

### Core Functionality
- **Dynamic Help Generation**: Automatically discovers all available commands
- **Multi-language Support**: Localized help text through LanguageManager
- **Cog Organization**: Groups commands by their cog/module
- **Rich Embed Display**: Professional embed formatting with descriptions

### Key Components
- `HelpCog` class - Main cog implementation
- `help` slash command - Primary user interface
- Command discovery and enumeration
- Multi-language content adaptation

## Commands

### `/help`
Displays comprehensive help information including:
- **All Available Commands**: Complete list of slash commands
- **Cog Descriptions**: Module functionality summaries
- **Command Descriptions**: Individual command usage details
- **Localized Content**: Help text in user's preferred language

**Parameters**: None

**Response**: Rich embed with organized command listings

## Technical Implementation

### Class Structure
```python
class HelpCog(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    async def help_command(self, interaction: discord.Interaction)
```

### Help Generation Process

#### Command Discovery
1. Iterate through all loaded cogs (`self.bot.cogs`)
2. Extract slash commands from each cog (`cog.get_app_commands()`)
3. Collect command metadata (name, description)
4. Organize by cog categories

#### Content Localization
1. Detect user's guild language preference
2. Retrieve translated command descriptions
3. Fallback to original descriptions if translations unavailable
4. Apply cog description translations

#### Embed Formatting
1. Create structured embed with title and description
2. Add fields for each cog and its commands
3. Format command listings with descriptions
4. Apply appropriate styling and colors

### Multi-language Support

#### Translation Priority
1. **Primary**: LanguageManager translations for commands
2. **Secondary**: Original command descriptions
3. **Fallback**: Default localization or "No description"

#### Supported Languages
- Traditional Chinese (zh_TW)
- Simplified Chinese (zh_CN)  
- English (en_US)
- Japanese (ja_JP)

## Display Format

### Embed Structure
```yaml
Title: Command Help
Description: Available bot commands overview
Color: Discord Blue

Fields:
  - Cog Name (Cog Description)
    - Command list with descriptions
```

### Command Listing Format
```
**{CogName}** ({CogDescription})
`/{command_name}`: {command_description}
```

### Localization Examples
- **Title**: "Command Help" / "指令幫助"
- **Description**: "Display all available commands" / "顯示所有可用指令的詳細資訊"
- **No Description**: "No description available" / "無描述"

## Error Handling

### Robust Fallback System
- Graceful handling when LanguageManager unavailable
- Safe attribute access for cog descriptions
- Default values for missing translations
- Error reporting through `func.report_error()`

### Content Safety
- Validation of cog command collections
- Safe string handling for all text content
- Protection against malformed embed data

## Performance Considerations

### Efficient Command Discovery
- Single iteration through all cogs
- Minimal API calls for command metadata
- Cached cog collections where possible
- Async operations for non-blocking execution

### Memory Management
- Lazy loading of translation data
- Efficient embed field management
- Cleanup of temporary data structures

## Security & Permissions

### Access Control
- Public command - no special permissions required
- Read-only access to bot command structure
- No sensitive system information exposed

### Content Filtering
- Safe display of public command information
- No implementation details revealed
- User-friendly formatting only

## Usage Examples

### Basic Usage
```
User: /help
Bot: [Rich embed with all available commands organized by cog]
```

### Expected Output Structure
```
📖 Command Help
Available bot commands overview

**Music** (YouTube music player with queue management)
`/play`: Play music from YouTube
`/skip`: Skip to next song
`/mode`: Set playback mode

**Help** (Command help system)
`/help`: Display all commands

**BotInfo** (Bot information display)
`/botinfo`: Show bot statistics
```

## Related Files

- `cogs/help.py` - Main implementation
- `LanguageManager` - Multi-language system
- `Translation files` - User interface localization
- `All cog modules` - Source for command discovery

## Future Enhancements

Potential improvements:
- Command usage statistics
- Advanced search functionality
- Help pagination for large command sets
- Interactive command selection
- Custom help categories
- Command alias support