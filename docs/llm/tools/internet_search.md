# Internet Search Tools

## Overview

The `InternetSearchTools` class provides LangChain-compatible tools for performing various types of internet searches using the InternetSearchCog. It supports multiple search types and integrates with Gemini grounding when available.

## Class: InternetSearchTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

**Parameters:**
- `runtime`: Orchestrator request containing bot, message, and logger

**Description:**
Initializes the tools container with runtime context for Discord integration and search operations.

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: List containing the internet_search tool with runtime context

**Description:**
Returns a list of LangChain tools bound to the current runtime context.

### Tool: internet_search

```python
@tool
async def internet_search(
    query: str,
    search_type: Literal["general", "youtube", "eat"] = "general",
    search_instructions: str = ""
) -> str:
```

**Parameters:**
- `query`: The search query string to process
- `search_type`: Type of search to perform
  - `"general"`: General web search
  - `"youtube"`: YouTube video search
  - `"eat"`: Food/restaurant search
- `search_instructions`: Optional short instructions for the grounding agent

**Returns:**
- `str`: Search result with provider and duration metadata

**Purpose:**
Performs internet search with support for Gemini grounding and structured search instructions.

**Search Types:**

1. **General Search**: `"general"`
   - Standard web search
   - Uses Google search engine
   - Supports complex queries

2. **YouTube Search**: `"youtube"`
   - Video-specific search
   - Returns video results
   - Integrates with YouTube platform

3. **Food/Eating Search**: `"eat"`
   - Restaurant and food-related search
   - Local business focus
   - E-commerce integration

**Gemini Grounding Integration:**

**Provider Selection:**
```python
# Determine preferred provider based on environment
gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
preferred_provider = "gemini" if gemini_key else "selenium"
```

**Search Instructions Processing:**
```python
# If higher-level model provided search instructions, prepend them
query_to_pass = f"{search_instructions}\n\n{query}" if search_instructions else query
```

**Instruction Examples:**
- `"prefer official sources"`
- `"only use sources from the last 2 years"`
- `"return output as JSON with keys answer/sources/highlights"`

**Performance Monitoring:**

**Timing and Provider Tracking:**
```python
start_ts = time.time()
result = await cog.internet_search(...)
duration = time.time() - start_ts
used_provider = preferred_provider

# Return result with metadata
return f"[provider={used_provider} duration={duration:.2f}s] {result}"
```

**Metadata Response Format:**
```
[provider=gemini duration=2.34s] Search results here...
```

**Error Handling:**

**Comprehensive Error Recovery:**
1. **Bot Instance Check**: Validates bot availability
2. **Cog Validation**: Ensures InternetSearchCog is loaded
3. **Network Error Handling**: Catches external API failures
4. **Graceful Degradation**: Returns error messages on failures

**Error Scenarios:**
- Bot instance not available
- InternetSearchCog not found
- Network connectivity issues
- API key problems
- Invalid search parameters

**Discord Integration:**

**Context Extraction:**
```python
message = getattr(runtime, "message", None)
guild_id = None
if message and getattr(message, "guild", None):
    guild_id = str(message.guild.id)

# Pass through to cog with context
result = await cog.internet_search(
    ctx=message,
    query=query_to_pass,
    search_type=search_type,
    message_to_edit=message_to_edit,
    guild_id=guild_id,
)
```

## Integration

The InternetSearchTools is used by:
- **ToolsFactory** for dynamic tool loading
- **LangChain agents** for information retrieval
- **Orchestrator** for search capabilities

## Dependencies

- `logging`: For operation monitoring
- `os`: For environment variable access
- `time`: For performance measurement
- `langchain_core.tools`: For tool integration
- `InternetSearchCog`: For search functionality
- `function.func`: For error reporting

## Usage Examples

**Basic Search:**
```python
# Simple search query
result = await internet_search("Python web frameworks")
```

**YouTube Search:**
```python
# Search for videos
result = await internet_search("Python tutorial", search_type="youtube")
```

**Structured Search:**
```python
# Search with specific instructions
result = await internet_search(
    query="React vs Vue.js comparison",
    search_instructions="Only use official documentation sources",
    search_type="general"
)
```

**Food Search:**
```python
# Local restaurant search
result = await internet_search("best sushi restaurants Tokyo", search_type="eat")
```

## Performance Considerations

**Provider Optimization:**
- Automatic provider selection based on API key availability
- Gemini grounding when available for enhanced results
- Selenium fallback for broader compatibility

**Caching Strategy:**
- Results may be cached by the underlying InternetSearchCog
- Guild-specific caching for improved performance
- Duration tracking for monitoring and optimization

**Error Resilience:**
- Non-fatal error handling prevents agent failures
- Detailed error reporting for debugging
- Graceful fallback mechanisms