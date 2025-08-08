# Memory Commands Cog

**File:** [`cogs/memory_commands.py`](cogs/memory_commands.py)

This cog provides the user-facing slash commands for interacting with the bot's memory system. It allows users to search, view statistics, and manage the memory associated with their channels.

## Dependencies

This cog is the command interface for the much larger **[Memory System](./memory/index.md)**. It relies on the `MemoryManager` instance being available on the bot object.

## Commands

### `/memory-search`

Searches the memory of the current channel for relevant past messages.

*   **Parameters:**
    *   `query` (str): The keyword or sentence to search for.
    *   `search_type` (Optional[str]): The type of search to perform. Defaults to `hybrid`.
        *   `semantic`: Searches based on the meaning of the query.
        *   `keyword`: Searches for exact keywords.
        *   `hybrid`: A combination of semantic and keyword search.
    *   `limit` (Optional[int]): The maximum number of results to return (1-20). Defaults to 10.
    *   `days_ago` (Optional[int]): Restricts the search to the last N days. Defaults to 0 (no limit).
*   **Returns:** An embed containing the search results, including snippets of the messages, timestamps, and relevance scores.

### `/memory-stats`

Displays statistics about the memory system's current state.

*   **Returns:** An embed showing:
    *   **Basic Info:** Total number of channels and messages indexed.
    *   **Performance:** Average query time, cache hit rate, and total storage size.
    *   **System Status:** Whether the memory and vector search systems are enabled, and the current configuration profile.

### `/memory-config`

Shows the current configuration of the memory system.

*   **Returns:** An embed detailing the active configuration profile, including the embedding model, hardware settings, and system settings like caching and optimization.

### `/memory-clear`

Clears all stored memories for the current channel.

*   **Parameters:**
    *   `confirm` (str): The user must type "CONFIRM" to proceed with this destructive action.
*   **Permissions:** Manage Channels
*   **Note:** This is a high-privilege command and will permanently delete data for the channel.