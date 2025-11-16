# Internet Search Cog Documentation

## Overview

The Internet Search cog provides comprehensive web search capabilities through Discord commands. It enables users to perform searches using various search engines and APIs, with features for result filtering, content summarization, and intelligent information retrieval across multiple sources.

## Features

### Core Functionality
- **Multi-Engine Search**: Support for multiple search engines (Google, Bing, DuckDuckGo)
- **Content Filtering**: Filter results by date, language, and content type
- **Result Summarization**: AI-powered summarization of search results
- **Smart Query Processing**: Intelligent query enhancement and expansion
- **Caching System**: Cache frequently searched queries for performance
- **Multi-language Support**: Full localization of search interfaces and results

### Key Components
- `InternetSearch` class - Main cog implementation
- Multi-engine search engine adapter
- Content analysis and summarization system
- Query processing and enhancement
- Result caching and optimization

## Commands

### `/search`
Performs a web search and displays results in an organized format.

**Parameters**:
- `query` (string, required): Search query/keywords
- `engine` (string, optional): Search engine to use (google, bing, duckduckgo, all)
- `limit` (int, optional, default: 5): Number of results to return (1-10)
- `include_summary` (boolean, optional, default: true): Include AI-generated summary

**Usage Examples**:
```
/search query:"latest python tutorials" engine:"google" limit:8
/search query:"machine learning algorithms" include_summary:true
/search query:"discord bot development" engine:"bing" limit:5
```

**Required Permissions**: None (public access)

### `/news`
Searches for recent news articles on a specific topic.

**Parameters**:
- `topic` (string, required): News topic or keywords
- `date_range` (string, optional): Time range (today, week, month, year)
- `category` (string, optional): News category (technology, sports, politics, etc.)
- `limit` (int, optional, default: 5): Number of articles to return (1-15)

**Usage Examples**:
```
/news topic:"artificial intelligence" date_range:"week" category:"technology"
/news topic:"climate change" date_range:"month"
/news topic:"gaming news" limit:8
```

**Required Permissions**: None (public access)

### `/quick_facts`
Provides quick facts and information on a specific topic.

**Parameters**:
- `topic` (string, required): Topic for quick facts
- `detail_level` (string, optional): Detail level (basic, detailed, comprehensive)

**Usage Examples**:
```
/quick_facts topic:"Python programming" detail_level:"detailed"
/quick_facts topic:"Bitcoin" detail_level:"basic"
/quick_facts topic:"Machine learning" detail_level:"comprehensive"
```

**Required Permissions**: None (public access)

## Technical Implementation

### Class Structure
```python
class InternetSearch(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    
    # Command handlers
    async def search_command(self, interaction: discord.Interaction, 
                            query: str, engine: str = "google", limit: int = 5,
                            include_summary: bool = True)
    async def news_command(self, interaction: discord.Interaction,
                          topic: str, date_range: str = "week", 
                          category: str = None, limit: int = 5)
    async def quick_facts_command(self, interaction: discord.Interaction,
                                 topic: str, detail_level: str = "basic")
    
    # Core search functionality
    async def search_web(self, query: str, engine: str = "google", limit: int = 5) -> List[SearchResult]
    async def search_news(self, topic: str, date_range: str = "week", limit: int = 5) -> List[NewsResult]
    async def get_quick_facts(self, topic: str, detail_level: str = "basic") -> Dict[str, Any]
    
    # Search engines
    async def google_search(self, query: str, limit: int = 5) -> List[SearchResult]
    async def bing_search(self, query: str, limit: int = 5) -> List[SearchResult]
    async def duckduckgo_search(self, query: str, limit: int = 5) -> List[SearchResult]
```

### Data Models
```python
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class SearchEngine(Enum):
    GOOGLE = "google"
    BING = "bing"
    DUCKDUCKGO = "duckduckgo"
    ALL = "all"

class ContentType(Enum):
    GENERAL = "general"
    NEWS = "news"
    ACADEMIC = "academic"
    IMAGES = "images"
    VIDEOS = "videos"

@dataclass
class SearchResult:
    id: str
    title: str
    url: str
    description: str
    snippet: str
    engine: SearchEngine
    published_date: Optional[datetime] = None
    language: str = "en"
    content_type: ContentType = ContentType.GENERAL
    score: float = 0.0
    metadata: Dict[str, Any] = None
```

### Multi-Engine Search System
```python
import aiohttp
import asyncio
from typing import List, Dict, Optional
import json
import hashlib
from urllib.parse import quote_plus

class SearchEngineAdapter:
    def __init__(self):
        self.engines = {
            'google': self.google_search,
            'bing': self.bing_search,
            'duckduckgo': self.duckduckgo_search
        }
        
        self.api_keys = {
            'google': self.get_google_api_key(),
            'bing': self.get_bing_api_key()
        }

    async def google_search(self, query: str, limit: int = 5) -> List[SearchResult]:
        """Perform Google Custom Search API query"""
        
        api_key = self.api_keys.get('google')
        search_engine_id = self.get_google_search_engine_id()
        
        if not api_key or not search_engine_id:
            return await self._fallback_search(query, limit)
        
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': api_key,
            'cx': search_engine_id,
            'q': query,
            'num': min(limit, 10),  # Google max is 10
            'safe': 'active',
            'fields': 'items(title,link,snippet,displayLink,formattedUrl)'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []
                        
                        for item in data.get('items', []):
                            result = SearchResult(
                                id=hashlib.md5(item['link'].encode()).hexdigest(),
                                title=item.get('title', ''),
                                url=item.get('link', ''),
                                description=item.get('snippet', ''),
                                snippet=item.get('snippet', ''),
                                engine=SearchEngine.GOOGLE,
                                metadata={'displayLink': item.get('displayLink')}
                            )
                            results.append(result)
                        
                        return results
                    else:
                        await func.report_error(f"Google API error: {response.status}", "google_search")
                        return []
                        
        except Exception as e:
            await func.report_error(e, "google_search")
            return []

    async def _fallback_search(self, query: str, limit: int) -> List[SearchResult]:
        """Fallback search when APIs are unavailable"""
        return []
```

## Error Handling

### Search Error Management
```python
async def handle_search_error(self, interaction, error, query: str, engine: str):
    """Handle search errors with user-friendly messages"""
    
    error_messages = {
        "api_key_missing": f"Search service not configured. Please contact the bot administrator.",
        "rate_limit_exceeded": f"Search rate limit exceeded. Please wait a moment before searching again.",
        "quota_exceeded": f"Search quota exceeded for {engine}. Please try again later.",
        "network_error": f"Unable to connect to {engine} search service. Please check your connection.",
        "no_results": f"No search results found for '{query}'. Try different keywords.",
        "invalid_query": f"Search query '{query}' is too short or contains invalid characters.",
        "service_unavailable": f"{engine} search service is temporarily unavailable.",
        "timeout": f"Search request timed out. Please try a simpler query."
    }
    
    await interaction.response.send_message(error_messages.get("network_error", "Search failed"), ephemeral=True)
    await func.report_error(error, f"search_{engine}")
```

## Usage Examples

### Basic Web Search
```
User: /search query:"python web development tutorial"
Bot: ## Search Results for: python web development tutorial

**Key Topics:** python, web, development, tutorial, framework

**Key Information:**
• Learn Python web development with Flask and Django frameworks
• Comprehensive tutorials covering Flask basics to advanced concepts
• Step-by-step guide for building web applications with Python

**Sources:** realpython.com, docs.python.org, freecodecamp.org

[Followed by individual search results with titles, URLs, and descriptions]
```

### News Search
```
User: /news topic:"artificial intelligence breakthroughs" date_range:"week" category:"technology"
Bot: ## AI News Results

**Recent AI Breakthroughs:**

• **OpenAI Releases GPT-5** - New language model achieves unprecedented performance
• **Google's Gemini Integration** - Advanced AI assistant now available
• **AI in Healthcare** - New diagnostic tools show promising results

**Sources:** techcrunch.com, arstechnica.com, venturebeat.com
```

## Configuration Options

### API Settings
```python
# Configuration in addons/settings.py
SEARCH_CONFIG = {
    "engines": {
        "google": {
            "enabled": True,
            "api_key": "your_google_api_key",
            "search_engine_id": "your_custom_search_engine_id",
            "rate_limit": 100
        },
        "bing": {
            "enabled": True,
            "api_key": "your_bing_api_key",
            "rate_limit": 1000
        }
    },
    "search_limits": {
        "default_results": 5,
        "max_results": 10
    }
}
```

## Related Files

- `cogs/internet_search.py` - Main implementation
- `translations/en_US/commands/internet_search.json` - English translations
- `LanguageManager` - Translation system
- `addons.tokens` - API key management

## Future Enhancements

Potential improvements:
- **AI-Powered Search**: Use AI to understand search intent
- **Image Search**: Add image search capabilities
- **Academic Search**: Specialized search for research papers
- **Personalized Search**: Learn from user search history
- **Real-time Search**: Live trending topics and breaking news