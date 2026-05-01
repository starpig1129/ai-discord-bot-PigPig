# LLM Memory Architecture

## Overview

The PigPig Bot employs a **Dual Memory System** to provide the LLM with rich, multi-layered context. This system ensures that the AI can remember past interactions, understand user-specific preferences, and leverage shared knowledge across channels and guilds.

## Memory Types

| Memory Type | Module | Persistence | Description |
|-------------|--------|-------------|-------------|
| **Short-Term** | `short_term.py` | Transient | Recent message history from the current channel. |
| **Episodic** | `episodic.py` | Long-term | Semantically relevant fragments from past conversations (Vector Search). |
| **Procedural** | `procedural.py` | Long-term | User-specific instructions, preferences, and interaction history. |
| **Knowledge** | `knowledge.py` | Long-term | Shared facts, memes, and rules for a specific guild or channel. |

## Data Flow

When a user sends a message, the `ContextManager` triggers all memory providers in parallel:

1. **Short-Term**: Fetches the last 10-20 messages to provide immediate conversational flow.
2. **Episodic**: Performs a vector search to find "ghosts of the past" that relate to the current query.
3. **Procedural**: Fetches the user's stored "personality" and behavioral instructions.
4. **Knowledge**: Injects server-specific rules or context.

These are then combined into a structured prompt that is sent to the LLM.

## Design Philosophy

- **Async Parallelism**: All memory providers run concurrently to minimize latency.
- **Silent Failures**: If a memory provider fails (e.g., database timeout), it returns an empty result instead of crashing the orchestration.
- **Context Prioritization**: Short-term memory has the highest priority for coherence, while episodic memory provides "wisdom" from previous months or years of interaction.

---
*For technical implementation details, refer to the specific memory provider documentation.*