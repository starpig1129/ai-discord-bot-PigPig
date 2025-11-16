# Short-Term Memory Provider

## Overview

The `ShortTermMemoryProvider` is responsible for fetching and formatting recent conversation messages from Discord channels, converting them into LangChain-compatible message objects for LLM processing.

## Class: ShortTermMemoryProvider

### Constructor

```python
def __init__(self, bot: Any, limit: int = 10):
```

**Parameters:**
- `bot`: Discord bot instance for message access
- `limit`: Maximum number of recent messages to fetch (default: 10)

**Validation:**
The `limit` parameter must be a positive integer. Raises `ValueError` if invalid.

**Description:**
Initializes the provider with bot instance and message limit. The limit determines how many recent messages to fetch from channel history.

### Methods

#### `async def get(self, message: discord.Message) -> List[BaseMessage]`

**Parameters:**
- `message`: Discord message object representing the current context

**Returns:**
- `List[BaseMessage]`: List of LangChain BaseMessage objects (HumanMessage/AIMessage)

**Description:**
Fetches recent messages from the channel and converts them to LangChain format. Messages are ordered from oldest to newest.

**Message Processing:**

1. **History Fetching:**
   ```python
   history = [msg async for msg in message.channel.history(limit=self.limit)][1:]
   history.reverse()
   ```
   - Excludes the current bot message (index 1 onwards)
   - Reverses to get chronological order (oldest to newest)

2. **Message Content Analysis:**
   Each message is processed to extract:
   - Author information (name, user ID, message ID)
   - Content text (with bot mentions removed)
   - Reactions
   - Reply references
   - Attachments (images, videos, audio, PDFs)
   - Timestamps

3. **LangChain Message Creation:**
   ```python
   if msg.author.bot:
       result.append(AIMessage(content=content_parts))
   else:
       result.append(HumanMessage(content=content_parts))
   ```

**Content Formatting:**

**Text Content Format:**
```
[AuthorName | UserID:123 | MessageID:456] <som> Message content <eom> [reactions: 😀👍 | reply_to: 789 | timestamp: 1234567890]
```

**Multimodal Support:**
- **Images**: `{"type": "image", "url": "https://...", "mime_type": "image/png"}`
- **Videos**: `{"type": "video", "url": "https://...", "mime_type": "video/mp4"}`
- **Audio**: `{"type": "audio", "url": "https://...", "mime_type": "audio/mp3"}`
- **Files**: `{"type": "file", "url": "https://...", "mime_type": "application/pdf"}`

**Error Handling:**
- All exceptions are reported using `func.report_error()`
- Returns empty list on failure to maintain system resilience

## Integration

This provider works with the Discord bot's message history API to provide conversational context for LLM interactions. The formatted messages are used by the ContextManager to build system context.

## Dependencies

- `discord`: For Discord message objects
- `langchain_core.messages`: For BaseMessage, HumanMessage, AIMessage
- `function.func`: For error reporting
- `typing`: For type annotations
- `re`: For content cleaning (bot mention removal)

## Performance Considerations

- **Async Operations**: Uses async/await for non-blocking message fetching
- **Message Limiting**: Configurable limit to control memory usage
- **Batch Processing**: Fetches messages in a single async iteration
- **Content Cleaning**: Removes bot mentions to prevent recursive interactions