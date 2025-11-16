# Discord Message Sender Utility

## Overview

The `send_message.py` module provides a sophisticated Discord message handling system for LLM responses. It handles language conversion, streaming responses, message editing, and comprehensive error recovery for Discord bot interactions.

## Constants

### `_ALLOWED_MENTIONS = discord.AllowedMentions(...)`

**Configuration:**
- `users=True`: Allow user mentions
- `roles=False`: Disallow role mentions
- `everyone=False`: Disallow @everyone mentions
- `replied_user=True`: Allow replies to users

**Purpose:**
Controls mention permissions to prevent spam and ensure appropriate Discord behavior.

### `_UPDATE_INTERVAL = 0.5`

**Description:**
Time interval in seconds between message updates for streaming responses.

### `_HARD_LIMIT = 2000`

**Description:**
Hard limit for Discord message character count (Discord's limit).

### `_MAX_RETRIES = 3`

**Description:**
Maximum number of retry attempts for failed Discord operations.

## Language Conversion System

### `_CONVERTERS = {...}`

**Supported Languages:**
- `'zh_TW'`: OpenCC('s2twp') - Simplified to Traditional Chinese
- `'zh_CN'`: OpenCC('tw2sp') - Traditional to Simplified Chinese  
- `'en_US'`: None - English doesn't need conversion
- `'ja_JP'`: None - Japanese doesn't need conversion

**Purpose:**
Pre-compiled converters for efficient language transformation.

### `get_converter(lang: str) -> Optional[opencc.OpenCC]`

**Parameters:**
- `lang`: Language code

**Returns:**
- OpenCC converter instance or None

**Description:**
Returns the appropriate language converter for the specified language code.

## Core Functions

### `safe_edit_message(message, content, max_retries=_MAX_RETRIES) -> bool`

**Parameters:**
- `message`: Discord message to edit
- `content`: New content for the message
- `max_retries`: Maximum retry attempts

**Returns:**
- `bool`: True if successful, False if failed

**Description:**
Safely edits a Discord message with retry logic and sanitization.

**Features:**
- **Sanitization**: Removes accidental @everyone/@here mentions
- **Retry Logic**: Handles transient Discord API failures
- **Validation**: Prevents empty message edits

### `_safe_send_message(channel, content, files=None, max_retries=_MAX_RETRIES) -> discord.Message`

**Parameters:**
- `channel`: Discord channel to send message
- `content`: Message content
- `files`: Optional file attachments
- `max_retries`: Maximum retry attempts

**Returns:**
- `discord.Message`: Sent message object

**Description:**
Safely sends Discord message with comprehensive error handling.

**Error Handling:**
- **Empty Content**: Raises ValueError for empty content
- **HTTP Errors**: Retries with exponential backoff
- **Sanitization**: Prevents mention abuse

### `_get_processing_message(message, lang_manager, message_type='processing') -> str`

**Parameters:**
- `message`: Discord message for guild context
- `lang_manager`: Language manager for translations
- `message_type`: Type of processing message

**Returns:**
- `str`: Localized processing message

**Description:**
Gets localized "processing" or "continuation" messages based on server language settings.

**Message Types:**
- `'processing'`: "處理中..." (Processing...)
- `'continuation'`: "繼續輸出中..." (Continuing output...)

## Stream Processing System

### `_process_token_stream(streamer, converter, current_message, channel, message, lang_manager, update_interval=_UPDATE_INTERVAL)`

**Parameters:**
- `streamer`: Token stream (async or sync iterator)
- `converter`: OpenCC converter for language conversion
- `current_message`: Current Discord message being edited
- `channel`: Discord channel for sending messages
- `message`: Original Discord message for context
- `lang_manager`: Language manager for translations
- `update_interval`: Time interval between updates

**Returns:**
- `Tuple[str, discord.Message]`: (full message result, final Discord message)

**Description:**
Processes token stream and updates Discord messages at regular intervals.

**Stream Processing Features:**

**Token Extraction:**
```python
if hasattr(token, "content") and token.content:
    token_str = str(token.content)
```

**Content Filtering:**
- Uses `<som>` (start of message) and `<eom>` (end of message) markers
- Only displays content between markers
- Accumulates complete output for return value

**Update Logic:**
- **Time-Based Updates**: Updates every `update_interval` seconds
- **Content Buffering**: Accumulates content before updating
- **Length Management**: Creates continuation messages when exceeding Discord limits

**Message Markers:**
```python
# Display filtering
if '<som>' in display_str:
    is_capturing = True
    display_str = display_str.split('<som>', 1)[-1]

if '<eom>' in display_str:
    display_str = display_str.split('<eom>', 1)[0]
    is_capturing = False
```

## Main Message Handler

### `send_message(bot, message_to_edit, message, streamer, update_interval=_UPDATE_INTERVAL) -> str`

**Parameters:**
- `bot`: Discord bot instance
- `message_to_edit`: Optional existing message to edit
- `message`: Original Discord message for context
- `streamer`: Token stream iterator
- `update_interval`: Time interval between updates

**Returns:**
- `str`: Full message result string

**Description:**
Main function that consumes token stream and manages Discord message updates.

**Workflow:**

1. **Channel Setup**: Extracts Discord channel from message
2. **Language Detection**: Gets server language and appropriate converter
3. **Message Initialization**: Creates initial "processing" message if needed
4. **Stream Processing**: Handles token stream with time-based updates
5. **Error Handling**: Comprehensive error recovery and user feedback

**Language Detection Logic:**
```python
if message and message.guild:
    lang_manager = bot.get_cog('LanguageManager')
    if lang_manager:
        guild_id = str(message.guild.id)
        lang = lang_manager.get_server_lang(guild_id)
        converter = get_converter(lang)
```

**Error Recovery:**
```python
except Exception as exc:
    await func.report_error(exc, 'Error generating GPT response')
    error_message = '不知道該怎麼回覆你了...'
    # Attempt to send error message
```

## Utility Functions

### `_sanitize_response(text: str) -> str`

**Parameters:**
- `text`: Text content to sanitize

**Returns:**
- `str`: Sanitized text

**Description:**
Sanitizes response text to prevent accidental Discord mentions.

**Sanitization Rules:**
- `@everyone` → `＠everyone`
- `@here` → `＠here`

## Integration Architecture

**LanguageManager Integration:**
```python
lang_manager = bot.get_cog('LanguageManager')
if lang_manager:
    guild_id = str(message.guild.id)
    lang = lang_manager.get_server_lang(guild_id)
```

**Discord Integration:**
- Uses discord.py for message operations
- Respects Discord rate limits
- Handles message editing and creation
- Supports file attachments

**Error Handling:**
- Comprehensive try-catch blocks
- Async error reporting via `func.report_error()`
- Graceful degradation for missing dependencies
- User-friendly error messages

## Dependencies

- `asyncio`: For async operations
- `logging`: For operation monitoring
- `time`: For timing and intervals
- `discord`: For Discord API integration
- `opencc`: For language conversion
- `function.func`: For error reporting

## Usage Examples

**Basic Message Sending:**
```python
from llm.utils.send_message import send_message

# Send streaming response
result = await send_message(
    bot=bot_instance,
    message_to_edit=None,  # Create new message
    message=discord_message,
    streamer=token_stream,
    update_interval=0.5
)
```

**Editing Existing Message:**
```python
# Edit an existing message
result = await send_message(
    bot=bot_instance,
    message_to_edit=existing_message,
    message=discord_message,
    streamer=token_stream
)
```

**Language-Specific Processing:**
```python
# Automatic language detection and conversion
# zh_TW servers: Simplified → Traditional Chinese
# zh_CN servers: Traditional → Simplified Chinese
# Other languages: No conversion needed
```

## Performance Considerations

**Efficient Updates:**
- **Time-Based Throttling**: Prevents excessive API calls
- **Content Buffering**: Reduces update frequency
- **Rate Limit Compliance**: Respects Discord's rate limits

**Memory Management:**
- **Stream Processing**: Processes tokens incrementally
- **Content Filtering**: Only stores necessary content
- **Garbage Collection**: Proper cleanup of resources

**Error Resilience:**
- **Retry Logic**: Handles transient network issues
- **Graceful Degradation**: Continues operation despite failures
- **User Feedback**: Provides clear error messages

## Streaming Response Flow

**Message Flow:**
1. **Initial Message**: "處理中..." (Processing...)
2. **Streaming Updates**: Real-time content updates
3. **Continuation Messages**: When content exceeds Discord limits
4. **Final Message**: Complete processed response

**Language Conversion:**
1. **Token Processing**: Raw tokens from LLM
2. **Content Extraction**: Filter <som>/<eom> markers
3. **Language Conversion**: Apply OpenCC conversion
4. **Message Updates**: Send to Discord with sanitization

**Error Recovery:**
1. **Stream Failure**: Send accumulated content
2. **API Failure**: Retry with exponential backoff
3. **Complete Failure**: Send fallback error message