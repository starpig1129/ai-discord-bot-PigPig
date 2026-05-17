# File: `cogs/memory/interfaces/vector_store_interface.py`

## Overview
This module defines the interface for vector stores in the memory system. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `MemoryFragment`
Represents a single fragment of episodic memory, ready for storage and retrieval.

- **Attributes**:
  - `id` (`Optional[str]`): Class attribute.
  - `content` (`str`): Class attribute.
  - `query_key` (`str`): Class attribute.
  - `metadata` (`Dict[Tuple[str, Any]]`): Class attribute.
  - `score` (`Optional[float]`): Class attribute.

### `VectorStoreInterface`
Abstract base class for vector store implementations.

- **Methods**:
  - `add_memories(memories: List[MemoryFragment]) -> None`: Adds a list of memory fragments to the vector store.
  - `search_memories_by_vector(query_text: str, limit: int, user_id: Optional[str], channel_id: Optional[str], min_score: Optional[float]) -> List[MemoryFragment]`: Search memories using vector similarity.
  - `search_memories_by_keyword(query_text: str, user_id: Optional[str], channel_id: Optional[str], k: int) -> List[MemoryFragment]`: Search memories using keyword / full-text payload matching.
  - `ensure_storage() -> None`: Ensure underlying storage exists and is ready (for example create collections
  - `search(vector_query: Optional[str], keyword_query: Optional[str], user_id: Optional[str], channel_id: Optional[str]) -> List[MemoryFragment]`: Performs a hybrid search using separate vector and keyword queries.
