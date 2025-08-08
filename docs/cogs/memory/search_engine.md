# Memory System - Search Engine

**File:** [`cogs/memory/search_engine.py`](cogs/memory/search_engine.py)

The `SearchEngine` is the core component responsible for retrieving relevant memories. It orchestrates the entire search process, combining different search strategies to find the most useful information for a given query.

## Data Classes

The module defines several `dataclass` objects to structure search-related data:

*   **`SearchType(Enum)`:** An enumeration for different search strategies (`SEMANTIC`, `KEYWORD`, `TEMPORAL`, `HYBRID`).
*   **`TimeRange`:** Represents a time window for filtering search results.
*   **`SearchQuery`:** A comprehensive object that encapsulates all parameters for a search request, including the query text, channel, search type, limits, and filters. It also includes a method to generate a unique cache key.
*   **`SearchResult`:** A container for the results of a search, including the list of messages, their relevance scores, and metadata about the search operation.

## `SearchEngine` Class

### `__init__(self, ...)`

Initializes the search engine with all its necessary dependencies.

*   **Dependencies:**
    *   `MemoryProfile`: The current configuration profile.
    *   `EmbeddingService`: To convert text queries into vectors for semantic search.
    *   `VectorManager`: To perform the actual vector similarity search.
    *   `DatabaseManager`: To retrieve message content and perform keyword searches.
    *   `RerankerService` (Optional): To refine and re-order search results for better relevance.
    *   `SearchCache` (Optional): To cache search results and speed up repeated queries.

### `search(self, query: SearchQuery) -> SearchResult`

This is the main public method of the class. It acts as a dispatcher, calling the appropriate internal search method based on the `query.search_type`.

### Search Strategies

#### `_semantic_search(self, ...)`

Performs a search based on the semantic meaning of the query.

1.  Converts the query text into a vector using the `EmbeddingService`.
2.  Uses the `VectorManager` to find the most similar conversation segment vectors in the index for that channel.
3.  Retrieves the full text messages corresponding to those segments from the `DatabaseManager`.
4.  (Optional) If the `RerankerService` is enabled, it takes the initial list of messages and re-orders them based on a more fine-grained relevance calculation, improving the quality of the final results.

#### `_keyword_search(self, ...)`

Performs a traditional keyword-based search.

1.  It extracts keywords from the query text.
2.  It uses the `DatabaseManager` to perform a full-text search for those keywords in the `messages` table.
3.  It calculates a relevance score for each result based on how well it matches the keywords.

#### `_hybrid_search(self, ...)`

Combines the strengths of both semantic and keyword searches.

1.  It executes both a `_semantic_search` and a `_keyword_search` in parallel.
2.  It then intelligently merges the results from both searches, removing duplicates and combining relevance scores to produce a final, comprehensive list of results.

## `SearchCache` Class

A simple in-memory cache with a Time-To-Live (TTL) policy. It stores the results of `SearchQuery` objects, using a hash of the query's parameters as the key. This significantly speeds up the system if the same or similar queries are made in quick succession.