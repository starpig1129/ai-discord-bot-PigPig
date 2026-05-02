# Episodic Memory Tools

## Overview

The `EpisodicMemoryTools` class provides LangChain-compatible tools that allow an LLM Agent to query the long-term episodic memory (semantic vector store) managed by the bot's `VectorManager`. This enables the bot to "remember" past conversations, even those that occurred months ago, by performing semantic search on historical fragments.

## Class: EpisodicMemoryTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

**Parameters:**
- `runtime`: Orchestrator request containing bot, message, and logger.

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: A list containing the `search_episodic_memory` tool.

### Tool: search_episodic_memory

```python
@tool
async def search_episodic_memory(
    vector_query: Optional[str] = None,
    keyword_query: Optional[str] = None,
    user_id: Optional[str] = None,
    global_search: bool = False
) -> str:
```

**Parameters:**
- `vector_query`: Natural-language semantic query (e.g., "What did we talk about regarding servers?").
- `keyword_query`: Exact-term query for precise matching (e.g., "Docker", "StarPig").
- `user_id`: Filter results to a specific Discord user ID.
- `global_search`: If `True`, searches all channels. If `False` (default), searches only the current channel.

**Returns:**
- `str`: A human-readable list of matching memory fragments with metadata (author, timestamp, jump URL).

**Purpose:**
Provides a hybrid search interface (Vector + Keyword) for deep conversational recall.

**Features:**
- **Hybrid Search**: Combines Concept-based recall (Vector) with Keyword filtering for high precision.
- **Context Awareness**: Automatically scopes searches to the current channel unless `global_search` is requested.
- **Metadata Richness**: Returns direct "Jump URLs" to the original Discord messages for verification.
- **Permission Scoping**: Can be filtered to specific users.

## Integration

- **VectorManager**: Direct integration with the bot's Qdrant/Chroma vector store.
- **MemoryFragment**: Standardized data structure for individual memory units.
- **Target Mode**: Routed to the **Info Agent** (`target_agent_mode = "info"`).

## Usage Examples

**Semantic Search:**
```python
# Finds conceptually related memories
result = await search_episodic_memory(vector_query="bot architecture discussion")
```

**Hybrid Search:**
```python
# Finds "architecture" discussions that mention "Gemini"
result = await search_episodic_memory(
    vector_query="bot architecture", 
    keyword_query="Gemini"
)
```

## Performance Considerations

- **Async Search**: Vector queries are executed asynchronously to prevent blocking the message flow.
- **Top-K Retrieval**: Only the most relevant fragments (typically top 5-10) are returned to prevent prompt overflow.
- **Deduplication**: Result fragments are usually filtered by the `VectorManager` to remove duplicates.

## Dependencies

- `cogs.memory.interfaces.vector_store_interface.MemoryFragment`: Standard memory structure.
- `VectorManager`: Bot-level service for handling embedding and search.
