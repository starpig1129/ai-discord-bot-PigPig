# GIF Tools Cog Documentation

## Overview

The GIF Tools cog provides comprehensive GIF search and processing capabilities for Discord users. It enables users to search for GIFs from various sources, process and edit GIFs, and share animated content with their Discord communities through a simple and intuitive interface.

## Features

### Core Functionality
- **Tenor API Integration**: Connects to the Tenor API for GIF search functionality
- **Randomized Results**: Configured to return random GIFs from search results for variety
- **Dual Interface**: Both slash command for users and programmatic API for other systems
- **Error Handling**: Robust error handling with user-friendly messages
- **Multi-language Support**: Full localization of search terms and results

### Key Components
- `GifTools` class - Main cog implementation
- Tenor API integration for GIF search
- Random result selection system
- Error handling and logging
- Translation support for internationalization

## Commands

### `/search_gif`
Searches for GIFs based on keywords and returns a random result.

**Parameters**:
- `query` (string, required): Search keywords for GIF content

**Usage Examples**:
```
/search_gif query:"happy cat"
/search_gif query:"celebration animation"
/search_gif query:"work motivation"
```

**Required Permissions**: None (public access)

## Technical Implementation

### Class Structure
```python
class GifTools(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    
    # Command handlers
    async def search_gif_command(self, interaction: discord.Interaction, query: str)
    
    # Core search functionality
    async def search_gif(self, query: str, limit: int = 1) -> List[str]
    async def get_gif_url(self, query: str) -> str
    
    # Utility methods
    def format_search_query(self, query: str) -> str
    async def handle_api_error(self, error, context: str)
```

### Core Search Methods

#### `async def search_gif(self, query: str, limit: int = 1) -> List[str]`
Core function that communicates with the Tenor API to search for GIFs.

**Parameters**:
- `query` (string): The search term for GIF content
- `limit` (integer): Number of results to fetch (defaults to 1)

**Returns**: List of GIF URLs. Returns empty list if search fails or no results found.

**Implementation Details**:
```python
async def search_gif(self, query: str, limit: int = 1) -> List[str]:
    try:
        # Prepare API request parameters
        params = {
            'key': self.tenor_api_key,
            'q': query,
            'limit': limit,
            'contentfilter': 'high',  # Safe content filter
            'media_filter': 'gif',    # GIF format only
            'random': True           # Random selection
        }
        
        # Make API request
        async with aiohttp.ClientSession() as session:
            async with session.get(self.tenor_api_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return [result['media'][0]['gif']['url'] for result in data['results']]
                else:
                    await func.report_error(f"Tenor API error: {response.status}", "gif_search")
                    return []
                    
    except Exception as e:
        await func.report_error(e, "search_gif")
        return []
```

#### `async def get_gif_url(self, query: str) -> str`
Convenience wrapper around `search_gif` designed for programmatic use by other systems.

**Parameters**:
- `query` (string): The search term for GIF content

**Returns**: Single GIF URL as string, or empty string if no GIF found.

**Implementation Details**:
```python
async def get_gif_url(self, query: str) -> str:
    """Programmatic interface for getting GIF URLs"""
    gif_urls = await self.search_gif(query)
    return gif_urls[0] if gif_urls else ""
```

### API Integration

#### Tenor API Configuration
```python
class TenorAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://tenor.googleapis.com/v2/search"
        self.rate_limit = 1000  # requests per hour
    
    async def search(self, query: str, limit: int = 1) -> List[Dict]:
        """Search GIFs using Tenor API"""
        
        headers = {
            'User-Agent': 'DiscordBot/1.0',
            'Accept': 'application/json'
        }
        
        params = {
            'key': self.api_key,
            'q': query,
            'limit': min(limit, 50),  # Tenor max is 50
            'contentfilter': 'high',  # Safe content only
            'media_filter': 'gif',    # GIF format
            'random': True            # Random selection
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, headers=headers, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        raise TenorAPIError(f"API returned status {response.status}")
                        
        except aiohttp.ClientError as e:
            raise TenorAPIError(f"Network error: {str(e)}")
```

## Error Handling

### Comprehensive Error Management
```python
async def handle_api_error(self, error, context: str):
    """Handle Tenor API errors with user-friendly messages"""
    
    error_messages = {
        "api_key_invalid": "GIF search service is not properly configured.",
        "network_error": "Unable to connect to GIF service. Please try again.",
        "quota_exceeded": "GIF search quota exceeded. Please try again later.",
        "no_results": "No GIFs found for your search. Try different keywords.",
        "service_unavailable": "GIF search service is temporarily unavailable."
    }
    
    # Log error for debugging
    await func.report_error(error, context)
    
    # Return appropriate error message
    if "401" in str(error):
        return error_messages["api_key_invalid"]
    elif "429" in str(error):
        return error_messages["quota_exceeded"]
    else:
        return error_messages["network_error"]
```

### Graceful Degradation
- **Empty Results**: Return empty list when no GIFs found
- **API Failures**: Fallback to default error handling
- **Network Issues**: Retry logic with exponential backoff
- **User Feedback**: Clear error messages for troubleshooting

## Usage Examples

### Basic GIF Search
```
User: /search_gif query:"happy cat"
Bot: 🐱 Here's a random happy cat GIF!
[Shows GIF with file attachment]
```

### Programmatic Usage
```python
# Usage in other cogs or AI systems
gif_tools = bot.get_cog("GifTools")
if gif_tools:
    gif_url = await gif_tools.get_gif_url("celebration")
    if gif_url:
        # Use GIF URL in your system
        pass
```

### Integration Examples
```python
# AI Response Enhancement
async def ai_response_with_gif(self, message, context):
    gif_tools = self.bot.get_cog("GifTools")
    if gif_tools:
        relevant_gif = await gif_tools.get_gif_url(message.content)
        if relevant_gif:
            await message.channel.send(relevant_gif)
```

## Advanced Features

### Smart Query Processing
```python
def format_search_query(self, query: str) -> str:
    """Format and clean search queries for better results"""
    
    # Clean and normalize query
    query = query.strip().lower()
    
    # Remove special characters except spaces
    import re
    query = re.sub(r'[^\w\s]', ' ', query)
    
    # Remove extra spaces
    query = ' '.join(query.split())
    
    # Add context if query is too short
    if len(query) < 3:
        query += " reaction"
    
    return query
```

### Result Filtering
```python
async def filter_results(self, results: List[Dict]) -> List[str]:
    """Filter and clean GIF results"""
    
    filtered_urls = []
    
    for result in results:
        try:
            # Extract GIF URL
            gif_data = result.get('media', [{}])[0].get('gif', {})
            url = gif_data.get('url')
            
            # Filter by size and quality
            if url and self.is_gif_suitable(url):
                filtered_urls.append(url)
                
        except (KeyError, IndexError) as e:
            await func.report_error(e, "result_filtering")
            continue
    
    return filtered_urls

def is_gif_suitable(self, url: str) -> bool:
    """Check if GIF meets quality and size requirements"""
    
    # Simple heuristics for GIF quality
    if 'nanogif' in url:  # Very small preview GIF
        return False
    
    # Could add more sophisticated checks
    # - File size limits
    # - Duration limits
    # - Quality thresholds
    
    return True
```

## Performance Optimization

### Caching System
```python
import hashlib
from functools import lru_cache

class GIFCache:
    def __init__(self):
        self.cache = {}
        self.timestamps = {}
        self.max_size = 100
        self.ttl = 3600  # 1 hour
    
    def get(self, query: str) -> Optional[str]:
        """Get cached GIF URL for query"""
        cache_key = hashlib.md5(query.encode()).hexdigest()
        
        if cache_key in self.cache:
            # Check if expired
            if datetime.now() - self.timestamps[cache_key] > timedelta(seconds=self.ttl):
                self._remove(cache_key)
                return None
            
            return self.cache[cache_key]
        
        return None
    
    def set(self, query: str, gif_url: str):
        """Cache GIF URL for query"""
        cache_key = hashlib.md5(query.encode()).hexdigest()
        
        # Remove oldest if cache is full
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.timestamps, key=lambda k: self.timestamps[k])
            self._remove(oldest_key)
        
        self.cache[cache_key] = gif_url
        self.timestamps[cache_key] = datetime.now()
```

### Rate Limiting
```python
from collections import defaultdict, deque
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, limit: int = 60, window: int = 60):
        self.limit = limit  # requests per window
        self.window = window  # window in seconds
        self.requests = defaultdict(deque)
    
    async def check_rate_limit(self, user_id: str) -> bool:
        """Check if user has exceeded rate limit"""
        now = datetime.now()
        key = str(user_id)
        
        # Clean old requests
        while (self.requests[key] and
               now - self.requests[key][0] > timedelta(seconds=self.window)):
            self.requests[key].popleft()
        
        # Check limit
        if len(self.requests[key]) >= self.limit:
            return False
        
        # Add current request
        self.requests[key].append(now)
        return True
```

## Configuration Options

### Bot Settings
```python
# Configuration in addons/settings.py
GIF_CONFIG = {
    "tenor_api_key": "your_tenor_api_key",
    "search_limit": {
        "default": 1,
        "max": 10,
        "min": 1
    },
    "cache_enabled": True,
    "cache_size": 100,
    "cache_ttl": 3600,  # 1 hour
    "rate_limit": {
        "requests": 60,
        "window": 60  # seconds
    }
}
```

### API Configuration
```python
# API settings
TENOR_CONFIG = {
    "base_url": "https://tenor.googleapis.com/v2",
    "content_filter": "high",  # safe, low, off
    "media_filter": "gif",
    "random": True,
    "timeout": 10,  # seconds
    "retry_attempts": 3
}
```

## Security Considerations

### Content Filtering
- **Safe Search**: Enable safe content filtering by default
- **API Key Protection**: Secure API key storage and usage
- **Rate Limiting**: Prevent abuse and excessive API usage
- **Input Validation**: Sanitize search queries

### User Protection
- **Query Validation**: Check for inappropriate search terms
- **Result Filtering**: Filter out potentially harmful content
- **API Key Security**: Never expose API keys in error messages
- **Rate Limit Enforcement**: Implement fair usage policies

## Integration Points

### With Other Cogs
```python
# Integration examples
from cogs.language_manager import LanguageManager
from cogs.userdata import UserData
from cogs.channel_manager import ChannelManager

# AI Enhancement
async def enhance_ai_response(self, context, response):
    gif_tools = self.bot.get_cog("GifTools")
    if gif_tools:
        # Add relevant GIF to AI responses
        relevant_gif = await gif_tools.get_gif_url(response.content)
        if relevant_gif:
            await context.channel.send(relevant_gif)
```

### External Systems
- **AI Systems**: Enhance AI responses with relevant GIFs
- **Content Management**: Automatic GIF insertion for content
- **Reaction Systems**: GIF-based reactions to messages
- **Entertainment Bots**: GIF integration for games and activities

## Related Files

- `cogs/gif_tools.py` - Main implementation
- `translations/en_US/commands/gif.json` - English translations
- `LanguageManager` - Translation system
- `addons.tokens` - API key management
- `addons.settings` - Configuration management

## Future Enhancements

Potential improvements:
- **Multiple Sources**: Add GIPHY and other GIF APIs
- **GIF Processing**: Basic editing capabilities (resize, crop, speed)
- **Advanced Search**: Category filtering and trending GIFs
- **User Favorites**: Save and manage favorite GIFs
- **GIF Creation**: Basic GIF creation from images
- **Smart Recommendations**: AI-powered GIF recommendations
- **Bulk Operations**: Search and download multiple GIFs
- **Analytics**: Track popular searches and trending content

## Troubleshooting

### Common Issues

**API Key Issues**:
- Verify Tenor API key is correctly configured
- Check API key has proper permissions
- Ensure API key is not expired

**Search Problems**:
- Try different search terms
- Check for rate limiting
- Verify internet connectivity

**Performance Issues**:
- Enable caching for better performance
- Monitor API response times
- Check rate limit settings

**Integration Issues**:
- Verify cog is loaded correctly
- Check for conflicts with other cogs
- Monitor error logs for debugging