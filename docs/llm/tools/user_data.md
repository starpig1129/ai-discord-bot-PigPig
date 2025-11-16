# User Memory Management Tools

## Overview

The `UserMemoryTools` class provides LangChain-compatible tools for managing user personal memory (procedural memory) through the UserDataCog. It enables agents to read and save user preferences, facts, and interaction rules that users have previously asked the bot to remember.

## Class: UserMemoryTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

**Parameters:**
- `runtime`: Orchestrator request containing bot, message, and logger

**Description:**
Initializes the user memory tools container with runtime context for Discord integration and memory management.

### Helper Methods

#### `_get_bot(self) -> Optional[Any]`

**Returns:**
- `Optional[Any]`: Bot instance if available, None otherwise

**Description:**
Safely retrieves the bot instance from the runtime with error logging.

#### `_get_cog(self) -> Optional[UserDataCog]`

**Returns:**
- `Optional[UserDataCog]`: UserDataCog instance if available, None otherwise

**Description:**
Safely retrieves the UserDataCog with validation and error handling.

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: List containing read_user_memory and save_user_memory tools

**Description:**
Returns LangChain tools bound to the current runtime context for user memory operations.

### Tool: read_user_memory

```python
@tool
async def read_user_memory(user_id: int) -> str:
```

**Parameters:**
- `user_id`: The Discord user's ID

**Returns:**
- `str`: Stored memory content, or "not found" message if no memory exists

**Purpose:**
Reads personal memory or preferences stored for a specific user.

**Use Cases:**
- Retrieve user's name or preferences
- Check previously saved interaction rules
- Access user's personal facts and information

**User ID Resolution:**

**Flexible ID Handling:**
```python
# Accept ints and int-like strings
effective_id = int(user_id)

# Fallback to message author if invalid ID provided
msg = getattr(runtime, "message", None)
if msg and getattr(msg, "author", None):
    effective_id = msg.author.id

# Handle interaction context
if isinstance(maybe_interaction, discord.Interaction) and getattr(maybe_interaction, "user", None):
    author_id = getattr(maybe_interaction.user, "id", None)
```

**Smart Fallback Logic:**
1. **Database Check**: Verify if user exists in database
2. **Message Author Fallback**: Use triggering message author if requested user not found
3. **Interaction Context**: Handle slash command interaction users
4. **String Format**: Convert to string for database storage

### Tool: save_user_memory

```python
@tool
async def save_user_memory(user_id: int, memory_to_save: str) -> str:
```

**Parameters:**
- `user_id`: The Discord user's ID
- `memory_to_save`: The new piece of information to remember

**Returns:**
- `str`: Confirmation message or error description

**Purpose:**
Saves or updates personal memory for a specific user with intelligent merging.

**Usage Guidelines:**
- **Explicit Requests Only**: Use only when user explicitly asks to remember something
- **Examples**: "My name is Bob", "Please call me Master", "I am a Python developer"
- **Intelligent Merging**: New information is merged with existing memory

**User ID Resolution:**

**Flexible ID Handling:**
```python
# Accept ints and int-like strings
effective_id = int(user_id)

# Fallback to message author if invalid
msg = getattr(runtime, "message", None)
if msg and getattr(msg, "author", None):
    effective_id = msg.author.id
```

**Display Name Resolution:**

**User Display Name Processing:**
```python
# Prefer cached user to avoid API calls
fetched_user = bot.get_user(int_id)
if not fetched_user:
    # Fallback to API fetch with error handling
    fetched_user = await bot.fetch_user(int_id)

# Extract display name with fallbacks
if fetched_user:
    display_name = getattr(
        fetched_user,
        "display_name", 
        getattr(fetched_user, "name", display_name)
    )
```

**Error Handling Scenarios:**

**Network Errors:**
- Discord HTTP exceptions (transient errors)
- User not found (deleted users)
- Rate limiting issues

**Data Errors:**
- Invalid user ID formats
- Empty memory content
- Database access failures

**Memory Operations:**

**Database Integration:**
```python
# Read operation
return await cog._read_user_data(
    str(effective_id),
    cast(Union[discord.Interaction, discord.Message], message_context),
)

# Save operation  
return await cog._save_user_data(
    str(effective_id),
    display_name,
    memory_to_save,
    cast(Union[discord.Interaction, discord.Message], message_context),
)
```

**Memory Processing Features:**
- **Intelligent Merging**: Combines new information with existing memory
- **Display Name Tracking**: Maintains user display names for context
- **Context Preservation**: Preserves interaction context for rich processing
- **Error Recovery**: Graceful handling of network and data errors

## Integration

The UserMemoryTools is used by:
- **ToolsFactory** for dynamic tool loading
- **LangChain agents** for personalized interactions
- **UserDataCog** for database operations
- **Orchestrator** for memory management functionality

## Dependencies

- `logging`: For operation monitoring
- `discord`: For Discord integration
- `langchain_core.tools`: For tool integration
- `UserDataCog`: For database memory operations
- `function.func`: For error reporting

## Usage Examples

**Reading User Memory:**
```python
# Read memory for specific user
result = await read_user_memory(user_id=123456789012345678)
# Returns: "User's stored preferences and facts"

# Read memory for message author
result = await read_user_memory(user_id="invalid_id")
# Returns: "Memory for message author"
```

**Saving User Memory:**
```python
# Save user preference
result = await save_user_memory(
    user_id=123456789012345678,
    memory_to_save="My name is Bob and I prefer casual conversation"
)
# Returns: "Memory saved successfully"

# Save from user request
result = await save_user_memory(
    user_id=987654321098765432,
    memory_to_save="Please call me Master"
)
# Returns: "Memory saved successfully"
```

## Privacy and Security Considerations

**User Privacy:**
- Respects user privacy settings
- Handles direct message contexts
- Validates user access permissions

**Data Protection:**
- Secure database storage
- User ID validation and sanitization
- Error handling prevents information leakage

**Spam Prevention:**
- Rate limiting for memory operations
- Content validation and sanitization
- Prevention of malicious memory flooding

**Memory Content Guidelines:**
- Only stores explicitly requested information
- Prevents injection of harmful content
- Maintains content integrity and accuracy