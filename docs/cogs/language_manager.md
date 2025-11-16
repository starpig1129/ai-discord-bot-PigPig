# LanguageManager Cog Documentation

## Overview

The LanguageManager is a sophisticated multi-language translation system that provides modular, cached translation services for the entire Discord bot. It supports lazy loading, multi-layer caching, and fallback mechanisms for optimal performance.

## Features

### Core Functionality
- **Multi-language Support**: Traditional Chinese, Simplified Chinese, English, Japanese
- **Modular Translation Structure**: Organized by translation keys and file paths
- **Lazy Loading**: On-demand loading of translation files
- **Multi-layer Caching**: Translation result caching with LRU eviction
- **Fallback System**: Graceful degradation when translations unavailable

### Key Components
- `LanguageManager` class - Main cog implementation
- `TranslationCache` class - LRU cache for translation results
- Server language configuration
- File indexing and path resolution
- Async background loading

## Commands

### `/set_language`
Sets the server's preferred language for all bot interactions.

**Parameters**:
- `language`: Language choice (繁體中文/简体中文/English/日本語)

**Permissions**: Administrator only

**Response**: Confirmation message with new language setting

### `/current_language`
Displays the current server language setting.

**Parameters**: None

**Response**: Current language name and confirmation

## Technical Implementation

### Class Structure
```python
class LanguageManager(commands.Cog):
    def __init__(self, bot: commands.Bot)
    async def cog_load(self)
    def translate(self, guild_id: str, *args, **kwargs) -> str
    def get_server_lang(self, guild_id: str) -> str
    def save_server_lang(self, guild_id: str, lang: str) -> bool
    
class TranslationCache:
    def __init__(self, max_size: int = 1000)
    def get(self, key: str) -> Optional[str]
    def put(self, key: str, value: str)
    def clear(self)
```

### Translation System Architecture

#### Multi-layer Data Structure
```
lang -> file_key -> path -> value
```

#### File Organization
```
translations/
├── zh_TW/
│   ├── common.json
│   ├── commands/
│   │   ├── botinfo.json
│   │   ├── help.json
│   │   └── ...
│   └── system/
├── zh_CN/
├── en_US/
└── ja_JP/
```

#### Path Resolution Strategy
1. **Exact Match**: Direct path lookup
2. **Partial Match**: Hierarchical path traversal
3. **Common Fallback**: Default to common.json
4. **Final Fallback**: Return key or error message

### Caching System

#### TranslationCache Features
- **LRU Eviction**: Least Recently Used cache management
- **Access Tracking**: Usage frequency and timing
- **Size Management**: Configurable cache limits
- **Thread Safety**: Concurrent access protection

#### Cache Performance
- **Multi-layer Caching**: Memory + disk caching
- **Key Generation**: `lang:path:format_hash` strategy
- **Automatic Invalidation**: Language changes trigger cache clear

### Lazy Loading System

#### Background Loading Process
1. **File Indexing**: Build path-to-file mappings
2. **Demand Loading**: Load files when first requested
3. **Worker Thread**: Async background file loading
4. **Cache Management**: Store loaded file contents

#### Loading Strategy
```python
# Phase 1: Load common files (fast startup)
_load_common_files(lang_codes)

# Phase 2: Build file index
_build_file_index(lang_code)

# Phase 3: Schedule lazy loading
_schedule_lazy_loading()
```

## Configuration

### Supported Languages
```yaml
zh_TW: "繁體中文"
zh_CN: "简体中文" 
en_US: "English"
ja_JP: "日本語"
```

### Server Configuration
- **Data Location**: `data/serverconfig/`
- **File Format**: JSON per server
- **Key**: Server ID
- **Value**: Language preference

### Cache Settings
- **Max Size**: 1000 entries (configurable)
- **Eviction Policy**: LRU (Least Recently Used)
- **TTL**: No expiration (manual clearing)

## Error Handling

### Robust Fallback System
1. **Translation Not Found**: Return key or default
2. **File Not Available**: Use cached or default values
3. **Cache Miss**: Load and cache result
4. **Initialization Issues**: Use hardcoded fallbacks

### Error Recovery
- Safe attribute access with `hasattr()`
- Try-catch blocks for all operations
- Asynchronous error reporting
- Graceful degradation to default language

## Performance Considerations

### Efficient Translation Lookup
- **Cached Results**: Avoid repeated file I/O
- **LRU Management**: Keep frequently used translations
- **Background Loading**: Non-blocking file operations
- **Memory Optimization**: Configurable cache limits

### Startup Optimization
- **Minimal Loading**: Load only essential files first
- **Async Operations**: Non-blocking initialization
- **Progressive Enhancement**: Features available as files load

## Security & Permissions

### Access Control
- **Language Setting**: Administrator permission required
- **Language Reading**: Public access (no restrictions)
- **Configuration Files**: Server-restricted access

### Data Protection
- **Server Isolation**: Configs separated by server ID
- **Safe File Operations**: Error handling for all I/O
- **Input Validation**: Sanitize all translation paths

## Integration Points

### With Other Cogs
```python
# Typical usage in other cogs
lang_manager = LanguageManager.get_instance(bot)
text = lang_manager.translate(
    guild_id, 
    "commands", 
    "command_name", 
    "description",
    parameter="value"
)
```

### Command Localization
- Automatic command name/description localization
- Option description translation
- Choice name localization
- Dynamic update when language changes

## Usage Examples

### Basic Translation
```python
# Server-specific translation
guild_id = str(interaction.guild_id)
text = self.lang_manager.translate(
    guild_id,
    "commands",
    "botinfo", 
    "title"
)
```

### With Parameters
```python
# Translation with formatting
text = self.lang_manager.translate(
    guild_id,
    "commands",
    "remind", 
    "confirm_setup",
    duration="5 minutes",
    user="<@123456789>"
)
```

### Fallback Handling
```python
# Manual fallback
translated = self.lang_manager.translate(guild_id, "key", "path")
if not translated or translated == "key":
    translated = "Default fallback text"
```

## Performance Metrics

### Cache Statistics
```python
cache_stats = lang_manager.get_cache_stats()
# Returns: {
#     "cache_size": 150,
#     "max_cache_size": 1000,
#     "loaded_files": 25,
#     "pending_loads": 3,
#     "supported_languages": 4
# }
```

### Monitoring
- Cache hit/miss ratios
- Loading times per language
- Memory usage tracking
- Error rates by language

## Related Files

- `cogs/language_manager.py` - Main implementation
- `translations/` - Translation file directories
- `data/serverconfig/` - Server language settings
- All other cogs - Translation consumers

## Future Enhancements

Potential improvements:
- Database-backed translations
- Translation editing interface
- Community translation contributions
- Advanced caching strategies
- Performance analytics dashboard
- Translation validation tools