# Memory System - Structured Context Builder

**File:** [`cogs/memory/structured_context_builder.py`](cogs/memory/structured_context_builder.py)

The `StructuredContextBuilder` is the final step in the memory retrieval process. Its purpose is to take the raw data retrieved by the `SearchEngine` and format it into a clean, human-readable, and contextually rich block of text. This formatted text is then provided to the LLM to inform its responses.

## `StructuredContextBuilder` Class

### `__init__(self)`

Initializes the builder, setting up formatting options like maximum lengths for different text elements and a dictionary of emojis for visual cues.

### `build_enhanced_context(self, user_info, conversation_segments, ...)`

This is the main method of the class. It takes the search results and constructs the final context string.

*   **Parameters:**
    *   `user_info` (Dict[str, UserInfo]): A dictionary of user information for participants in the conversation.
    *   `conversation_segments` (List[EnhancedSegment]): A list of the relevant conversation segments retrieved from the search.
*   **Process:**
    1.  It calls `_build_participant_section` to create a summary of the users involved in the conversation.
    2.  It calls `_build_conversation_section` to format the list of retrieved conversation segments.
    3.  It sorts these sections by priority (participant info is typically higher priority).
    4.  It combines the formatted sections into a single string.
    5.  It truncates the final string if it exceeds the `max_total_length` to ensure it fits within the LLM's context window.
*   **Returns:** A single, formatted string ready to be injected into an LLM prompt.

### Formatting Logic

The builder uses several helper methods to format the data in a way that is both compact and easy for the LLM to parse.

*   **`_format_user_info(...)`:** Formats information for a single user, including their Discord tag, display name, last active time, and a snippet of their stored user data.
*   **`_format_conversation_segment(...)`:** Formats a single conversation segment. This is a key part of the output, as it adds several visual cues:
    *   **Relevance Emoji:** An emoji (🔥, 📝, 💡) is added to indicate the semantic relevance score of the segment.
    *   **Participant Emoji:** An emoji (👤) is added if the segment involves one of the main participants.
    *   **Time Emoji:** An emoji (🕐) is added if the segment is from the last 24 hours.
    *   **Content:** The text of the segment is truncated to keep the context concise.
    *   **Metadata:** The user who sent the message and a formatted timestamp are included.

### Example Output

The final output is a markdown-formatted string that might look like this:

```markdown
📋 **對話參與者資訊**
• <@123456789> (JohnDoe) | 最後活躍: 5小時前
  └─ 資料: Prefers formal communication...
• <@987654321> (JaneDoe) | 最後活躍: 10分鐘前
  └─ 資料: Is the project lead for 'Project X'...

💬 **相關歷史對話**
🔥👤🕐 `[07-24 12:30]` <@987654321>: The deadline for Project X is confirmed for this Friday.
📝🕐 `[07-24 10:15]` <@123456789>: Can we get a status update on the server migration?