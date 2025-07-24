# Memory System - Conversation Segment Enhancer

**File:** [`cogs/memory/conversation_segment_enhancer.py`](cogs/memory/conversation_segment_enhancer.py)

The `ConversationSegmentEnhancer` is a post-processing module that refines the results returned by the `SearchEngine`. Its primary goal is to add a layer of contextual relevance to the search results, making them more useful for the `StructuredContextBuilder`.

## `ConversationSegmentEnhancer` Class

### `__init__(self, memory_manager: MemoryManager)`

Initializes the enhancer with an instance of the `MemoryManager`, which it uses to perform the initial search.

### `async search_enhanced_segments(self, search_context: SearchContext) -> List[EnhancedSegment]`

This is the main method of the class. It takes a `SearchContext` object, performs a search, and then enhances the results.

*   **Parameters:**
    *   `search_context` (SearchContext): A data class containing the search query, channel ID, and information about the current participants in the conversation.
*   **Process:**
    1.  It performs a standard search using the `memory_manager.search_memory()` method.
    2.  It passes the raw results to `_enhance_search_results()`.
    3.  The enhanced results are then passed to `_rank_segments_by_relevance()` for final scoring and sorting.
    4.  The top N results are returned.
*   **Returns:** A list of `EnhancedSegment` objects.

## Enhancement Logic

The "enhancement" process involves adding new metadata and calculating a more nuanced relevance score.

### `_enhance_search_results(...)`

This method converts the raw message dictionaries from the search result into `EnhancedSegment` data classes. The key step here is determining the `is_participant_related` flag. It checks if the author of a retrieved message is one of the active participants in the current conversation (as defined in the `search_context`).

### `_rank_segments_by_relevance(...)`

This method calculates a new, enhanced relevance score for each segment to provide a more context-aware ranking. The final score is a combination of several factors:

*   **Base Score:** The original relevance score from the `SearchEngine`.
*   **Participant Boost:** A significant score bonus (`participant_score_boost`) is added if `is_participant_related` is `True`. This prioritizes memories involving the people who are currently talking.
*   **Recency Boost:** A smaller bonus (`recency_score_boost`) is added for recent messages (within the last 7 days), with the bonus decreasing as the message gets older.
*   **Content Quality Boost:** A minor bonus is added for messages that are likely to be more meaningful (e.g., they are of a certain length, contain questions, or include specific keywords like "plan" or "issue").

The segments are then re-sorted based on this new, enhanced score before being returned.