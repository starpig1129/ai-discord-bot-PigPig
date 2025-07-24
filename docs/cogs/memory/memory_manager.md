# Memory System - Memory Manager

**File:** [`cogs/memory/memory_manager.py`](cogs/memory/memory_manager.py)

The `MemoryManager` is the central nervous system of the entire memory system. It acts as the primary entry point and orchestrator, initializing, coordinating, and providing a unified API for all other memory-related components.

## `MemoryManager` Class

### `__init__(self, bot, ...)`

The constructor initializes the manager and all its subordinate components.

*   **Initialization Process:**
    1.  Loads the memory system configuration from `optimization_config.json`.
    2.  Initializes the `DatabaseManager` to handle all SQLite operations.
    3.  Initializes the `EmbeddingService` to manage the loading and use of text embedding models.
    4.  Initializes the `VectorManager` to handle the storage and searching of vector indices.
    5.  Initializes the `SearchEngine`, which combines the embedding service and vector manager to perform searches.
    6.  Initializes the `TextSegmentationService` to group messages into logical conversation segments.

### Key Methods

#### `async initialize(self) -> bool`

Performs the main, asynchronous initialization of the memory system. This method is called once at bot startup. It loads configurations, sets up database connections, and prepares the vector search components.

#### `async store_message(self, message: discord.Message) -> bool`

This is the primary method for ingesting new information. It's called for each new message in a channel where memory is active.

*   **Process:**
    1.  It prepares the message data, cleaning and formatting the content.
    2.  It saves the message to the SQLite database via the `DatabaseManager`.
    3.  It passes the message to the `TextSegmentationService` to determine if a new conversation segment should be created or if the message belongs to an existing one.
    4.  If a segment is completed, it triggers the process to embed the segment's content and store the resulting vector.

#### `async search_memory(self, search_query: SearchQuery) -> SearchResult`

The main public method for retrieving memories.

*   **Parameters:**
    *   `search_query` (SearchQuery): A data class containing the search text, channel ID, search type, and other parameters.
*   **Process:**
    1.  It first checks the `SearchCache` for a recent, identical query.
    2.  If no cached result is found, it passes the query to the `SearchEngine`.
    3.  The `SearchEngine` performs the requested search (semantic, keyword, or hybrid).
    4.  The results are returned as a `SearchResult` object.
    5.  The new result is stored in the `SearchCache`.
*   **Returns:** A `SearchResult` data class containing the retrieved messages, relevance scores, and metadata about the search.

#### `async get_stats(self) -> MemoryStats`

Retrieves performance and usage statistics for the entire memory system, such as the total number of indexed messages, average query time, and cache hit rate.