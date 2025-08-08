# Memory System - Database

**File:** [`cogs/memory/database.py`](cogs/memory/database.py)

The `DatabaseManager` class is the foundational persistence layer for the memory system. It provides a thread-safe interface for all interactions with the SQLite database, handling everything from table creation to complex data queries.

## `DatabaseManager` Class

### `__init__(self, db_path)`

Initializes the database manager.

*   **Parameters:**
    *   `db_path` (str | Path): The file path for the SQLite database.
*   **Process:**
    1.  Ensures the parent directory for the database file exists.
    2.  Calls `_initialize_database` to set up the schema.
    3.  Lazily initializes the `UserManager` to avoid circular import issues.

### Key Features & Methods

#### Thread Safety

The manager uses a `threading.RLock` and a dictionary of connections keyed by thread ID (`threading.get_ident()`) to ensure that each thread gets its own dedicated database connection. This is crucial for preventing data corruption in a multi-threaded environment.

#### Connection Management

The `get_connection()` context manager provides a safe and reliable way to access a database connection. It handles connection pooling, transaction management (committing on success, rolling back on error), and ensures connections are properly managed.

#### Schema Definition

*   **`_create_tables(self, ...)`:** This method defines the entire database schema. It creates all necessary tables, including:
    *   `channels`: Stores information about channels where memory is active.
    *   `messages`: The primary table for storing individual message content and metadata.
    *   `embeddings`: Stores the vector embeddings associated with messages (though this is being superseded by segment-level embeddings).
    *   `users` & `user_profiles`: Tables for the `UserManager` to store user-specific data.
    *   `conversation_segments`: Stores metadata about logical chunks of conversation.
    *   `segment_messages`: A mapping table that links messages to their parent conversation segment.
*   **`_create_indexes(self, ...)`:** Creates indexes on frequently queried columns (like `channel_id` and `timestamp`) to dramatically speed up data retrieval.

#### Core Data Operations

*   **`store_message(self, ...)` / `add_messages(self, ...)`:** Methods for inserting single or multiple messages into the `messages` table. These also handle updating the `last_active` and `message_count` fields in the `channels` table.
*   **`get_messages(self, ...)` / `get_messages_by_ids(self, ...)`:** Methods for retrieving messages based on various criteria like channel, time range, or a list of specific message IDs.
*   **`create_conversation_segment(self, ...)`:** Creates a record for a new conversation segment in the `conversation_segments` table.
*   **`add_message_to_segment(self, ...)`:** Links a message to a segment in the `segment_messages` table.