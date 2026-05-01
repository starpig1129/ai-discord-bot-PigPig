# Episodic Memory Provider

## Overview

The `EpisodicMemoryProvider` implements a "long-term recall" mechanism. It uses semantic vector search to find past messages that are relevant to the user's current query, even if they occurred months ago.

## Core Logic

### 1. Query Pre-processing
- **Mention Removal**: Mentions (e.g., `<@123456>`) are stripped to prevent biased search results.
- **Short Message Skip**: Messages with fewer than 4 words are ignored to avoid searching for generic greetings like "hello" or "ok".

### 2. Vector Search
The provider interacts with the `vector_manager` (part of `cogs.memory`) to:
- Generate an embedding for the current message.
- Search the vector database for the top-k (default 3) most similar past messages in the current channel.

### 3. Formatting
Relevant fragments are formatted into a clear section for the LLM:
```text
--- Relevant Past Memories ---
[memory #1] User said: "I love pepperoni pizza" [[來源](jump_url)]
[memory #2] User said: "Pizza night on Friday?" [[來源](jump_url)]
--- End Past Memories ---
```
- **Source Linking**: Each memory fragment includes a Discord "Jump URL" and a relative timestamp (e.g., "3 months ago") using Discord's `<t:timestamp:R>` format.

## Performance Optimization

### TTL Caching
The provider maintains a thread-safe cache of recent search results:
- **Key**: `(channel_id, query_text)`
- **TTL**: 5 minutes (default).
- **Benefit**: Prevents redundant vector searches if the user repeats a query or if multiple agents need the same context.

### Async Execution
`EpisodicMemoryProvider.get()` is designed to run in parallel with other providers, ensuring that vector search latency does not block the entire bot response.

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `top_k` | 3 | Number of fragments to retrieve. |
| `max_chars` | 1500 | Maximum total length of the context string. |
| `cache_ttl` | 300.0 | Seconds before a cache entry expires. |

---
*This provider allows the bot to maintain a sense of history and "remember" facts that were never explicitly saved to procedural memory.*
