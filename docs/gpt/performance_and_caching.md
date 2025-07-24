# GPT System - Performance & Caching

**Files:**
*   [`gpt/performance_monitor.py`](gpt/performance_monitor.py)
*   [`gpt/processing_cache.py`](gpt/processing_cache.py)

This document covers the utilities responsible for monitoring the performance of the AI pipeline and caching results to improve response times and reduce costs.

## `PerformanceMonitor` Class

This class is a simple but effective tool for tracking the performance of various operations within the bot.

*   **`start_timer(name)` / `stop_timer(name)`:** These methods allow for timing specific code blocks. The `MessageHandler` uses this to measure key parts of the pipeline, such as `total_response_time`, `tool_execution_time`, and `llm_generation_time`.
*   **`increment_counter(name)`:** This method is used to count occurrences of specific events, such as `cache_hits` and `cache_misses`.
*   **`get_performance_stats()`:** This method aggregates all the collected data and returns a dictionary containing detailed statistics, including total counts, total time, average time, and max/min times for each timer. The results are displayed via the `/perf_stats` command.

## `ProcessingCache` Class

This class provides an in-memory cache to store the final results of the AI processing pipeline. Its main purpose is to prevent the bot from re-running the entire expensive pipeline (context building, tool selection, LLM calls) for identical user inputs that are made in quick succession.

*   **`_generate_cache_key(...)`:** Creates a unique hash key based on the user's input, their user ID, the channel ID, and any other relevant context.
*   **`get_cached_result(...)`:** Retrieves a result from the cache if it exists and has not expired (based on the TTL).
*   **`cache_result(...)`:** Stores a new result in the cache with a timestamp.
*   **LRU Cleanup:** The cache has a maximum size. When it becomes full, it automatically removes the least recently used (LRU) items to make space.
*   **Semantic Cache (Experimental):** The class also includes an experimental semantic cache. It stores the vector embeddings of user inputs and, if a new input is sufficiently similar to a cached one (above `semantic_threshold`), it will return the cached result.