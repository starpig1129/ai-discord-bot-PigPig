# Memory System

**Location:** [`cogs/memory/`](cogs/memory/)

The Memory System is a sophisticated, persistent long-term memory feature for the bot. It automatically captures, processes, and indexes conversations, enabling the bot to recall past interactions with high relevance and context.

## Core Components

The system is built upon several key, interconnected components:

*   **[Memory Manager](./memory_manager.md):** The central orchestrator of the entire system.
*   **[Database](./database.md):** The SQLite-based persistence layer for all textual data.
*   **[Embedding Service](./embedding_service.md):** Converts text into numerical vector representations.
*   **[Vector Manager](./vector_manager.md):** Manages the storage and retrieval of vector embeddings.
*   **[Search Engine](./search_engine.md):** Provides hybrid search capabilities (semantic, keyword, etc.).
*   **[Segmentation Service](./segmentation_service.md):** Groups messages into coherent conversational segments.
*   **[Structured Context Builder](./structured_context_builder.md):** Formats retrieved memories into a human-readable context for the LLM.
*   **[User Manager](./user_manager.md):** Manages data associated with individual users.

## Data Flow: Storing a Message

1.  A new message is sent in a channel where the memory system is active.
2.  The **[Memory Manager](./memory_manager.md)** receives the message.
3.  The message content and metadata are saved to the **[Database](./database.md)**.
4.  The message is passed to the **[Segmentation Service](./segmentation_service.md)**, which determines if the message concludes a conversational segment.
5.  Once a segment is complete, its content is sent to the **[Embedding Service](./embedding_service.md)** to be converted into a vector.
6.  The resulting vector is stored in a specialized index file by the **[Vector Manager](./vector_manager.md)**.

## Data Flow: Recalling a Memory

1.  The bot needs to recall a memory (e.g., to answer a question).
2.  A query is sent to the **[Memory Manager's](./memory_manager.md)** `search_memory` method.
3.  The **[Search Engine](./search_engine.md)** uses the **[Embedding Service](./embedding_service.md)** to convert the query into a vector.
4.  The **[Vector Manager](./vector_manager.md)** finds the most similar conversation segment vectors.
5.  The **[Database](./database.md)** retrieves the corresponding text messages for those segments.
6.  The **[Structured Context Builder](./structured_context_builder.md)** formats the retrieved messages and user data into a clean block of text.
7.  This final context is provided to the LLM to inform its response.