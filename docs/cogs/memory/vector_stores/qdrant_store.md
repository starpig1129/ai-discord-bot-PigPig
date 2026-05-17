# File: `cogs/memory/vector_stores/qdrant_store.py`

## Overview
Qdrant-based Vector Store using LangChain integration. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `QdrantStore`
LangChain Qdrant vector store wrapper.

- **Attributes**:
  - `settings` (`Any`): Instance attribute.
  - `embedding_model` (`Any`): Instance attribute.
  - `collection_name` (`Any`): Instance attribute.
  - `embedding_dim` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(settings: MemoryConfig, embedding_model: Optional[Embeddings]) -> None`: Executes __init__ operation.
  - `ensure_storage() -> None`: Ensure payload indexes exist.
  - `add_memories(memories: List[MemoryFragment]) -> None`: Add memories using LangChain's add_documents.
  - `search_memories_by_vector(query_text: str, limit: int, user_id: Optional[str], channel_id: Optional[str], min_score: Optional[float]) -> List[MemoryFragment]`: Vector similarity search with metadata filtering.
  - `search_memories_by_keyword(query_text: str, user_id: Optional[str], channel_id: Optional[str], k: int) -> List[MemoryFragment]`: Keyword search using Qdrant query API with payload filtering.
  - `search(vector_query: Optional[str], keyword_query: Optional[str], user_id: Optional[str], channel_id: Optional[str]) -> List[MemoryFragment]`: Hybrid search combining vector and keyword results.
  - `_report_error(error: Exception) -> None`: Helper to report errors.
