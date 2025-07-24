# Memory System - Segmentation Service

**File:** [`cogs/memory/segmentation_service.py`](cogs/memory/segmentation_service.py)

The `TextSegmentationService` is a crucial component that groups a continuous stream of messages into meaningful "conversation segments." Instead of treating each message as an independent memory, the system operates on these segments, which provides better context for semantic search.

## `TextSegmentationService` Class

### `__init__(self, db_manager, embedding_service, ...)`

Initializes the service with its dependencies, including the database manager (to get message history) and the embedding service (for semantic comparisons).

### `async process_new_message(self, ...)`

This is the main entry point for the service. It is called by the `MemoryManager` for each new message.

*   **Process:**
    1.  It checks if a new segment should be created by calling `_should_create_new_segment`.
    2.  If `True`, it finalizes the currently active segment for the channel (saving it to the database) and then starts a new one.
    3.  If `False`, it simply adds the new message to the currently active segment.
*   **Returns:** The completed `ConversationSegment` object if a segment was just finalized, otherwise `None`.

## Segmentation Strategies

The decision to create a new segment is determined by the `_should_create_new_segment` method, which uses a strategy defined in the system configuration (`SegmentationStrategy`).

### `_check_time_threshold(...)` (Time-Only Strategy)

This strategy creates a new segment if the time gap between the new message and the last message in the current segment exceeds a dynamic threshold. The threshold is calculated by `_calculate_dynamic_interval`, which creates shorter intervals for highly active channels and longer intervals for inactive ones.

### `_check_semantic_threshold(...)` (Semantic-Only Strategy)

This strategy creates a new segment if the semantic meaning of the new message is significantly different from the content of the current segment.

1.  It gets a representative text for the current segment (e.g., a summary or concatenation of messages).
2.  It uses the `EmbeddingService` to calculate the cosine similarity between the new message and the segment's representative text.
3.  If the similarity score is below the `similarity_threshold` from the configuration, a new segment is created.

### `_check_hybrid_threshold(...)` (Hybrid Strategy - Default)

This is the default and most robust strategy. It creates a new segment if **any** of the following conditions are met:
*   The time threshold is exceeded.
*   The semantic threshold is not met (i.e., the topic has changed).
*   The current segment has reached its maximum configured message count (`max_messages_per_segment`).

### `_finalize_current_segment(...)`

When a segment is completed, this method is called to perform final processing before it's saved. This includes:
*   Calculating the segment's overall vector representation (e.g., by averaging the embeddings of its messages).
*   Calculating a semantic coherence score for the segment.
*   Optionally, generating an AI summary of the segment.
*   Saving the completed segment and its vector to the database and vector index, respectively.