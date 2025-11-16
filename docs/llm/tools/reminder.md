# Reminder Management Tools

## Overview

The `ReminderTools` class provides LangChain-compatible tools for setting and managing reminders using the ReminderCog. It enables agents to schedule future notifications for users with flexible time specifications.

## Class: ReminderTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

**Parameters:**
- `runtime`: Orchestrator request containing bot, message, and logger

**Description:**
Initializes the reminder tools container with runtime context for Discord integration and scheduling capabilities.

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: List containing the set_reminder tool with runtime context

**Description:**
Returns a list of LangChain tools bound to the current runtime context.

### Tool: set_reminder

```python
@tool
async def set_reminder(
    time_str: str, message: str, user_id: Optional[int] = None
) -> str:
```

**Parameters:**
- `time_str`: Time specification string (e.g., "10m", "2h", "tomorrow 3pm")
- `message`: The reminder message content to be sent
- `user_id`: Optional Discord user ID to remind (defaults to message author)

**Returns:**
- `str`: A success message with reminder details, or an error message if scheduling failed

**Purpose:**
Schedules a reminder that will be sent to the specified user at the given time.

**Supported Time Formats:**

**Relative Time:**
- `"10m"`: 10 minutes from now
- `"2h"`: 2 hours from now  
- `"1d"`: 1 day from now
- `"30s"`: 30 seconds from now

**Absolute Time:**
- `"tomorrow 3pm"`: Tomorrow at 3 PM
- `"next Monday"`: Next Monday
- `"2024-01-15 14:30"`: Specific date and time
- `"friday 18:00"`: Friday at 6 PM

**Complex Expressions:**
- `"in 5 minutes"`: 5 minutes from now
- `"next week"`: One week from now
- `"every day at 9am"`: Daily recurring (if supported)

**Time Format Examples:**
```python
# Relative times
await set_reminder("10m", "Meeting starts in 10 minutes")
await set_reminder("2h", "Call your mom in 2 hours")
await set_reminder("1d", "Pay bills tomorrow")

# Absolute times  
await set_reminder("tomorrow 3pm", "Doctor appointment")
await set_reminder("2024-01-15 14:30", "Project deadline")

# Complex expressions
await set_reminder("in 5 minutes", "Coffee break")
await set_reminder("next Monday", "Team meeting")
```

**User Management:**

**Target User Determination:**
```python
# If user_id is not specified, use the requester
if user_id is None:
    if message_obj and getattr(message_obj, "author", None):
        target_user_id = message_obj.author.id
    else:
        target_user_id = None

# Fetch user object
target_user = (
    await bot.fetch_user(target_user_id)
    if target_user_id is not None
    else None
)
```

**User Context Features:**
- **Default Target**: Uses message author if user_id not specified
- **User Validation**: Fetches and validates user objects
- **Fallback Handling**: Graceful handling of user fetch failures
- **Private Messages**: Supports DMs with guild_id = "@me"

**Discord Context Integration:**

**Channel and Guild Information:**
```python
channel = getattr(message_obj, "channel", None)
guild_obj = getattr(message_obj, "guild", None)
guild_id = str(guild_obj.id) if guild_obj else "@me"
```

**Context Extraction:**
- **Channel Context**: Determines where reminder notification will be sent
- **Guild Context**: Tracks server-specific settings and permissions
- **DM Support**: Handles direct message reminders

**Scheduling Process:**

**Reminder Logic Delegation:**
```python
# Call ReminderCog scheduling logic
result = await cog._set_reminder_logic(
    channel=channel,
    target_user=target_user,
    time_str=time_str,
    message=message,
    guild_id=guild_id,
    interaction=None,
)
```

**Scheduling Features:**
- **Time Parsing**: Flexible time string interpretation
- **User Permissions**: Respects server permission settings
- **Duplicate Prevention**: Avoids duplicate reminder creation
- **Rich Formatting**: Supports Discord message formatting

**Error Handling:**

**Comprehensive Error Recovery:**
1. **Bot Instance Validation**: Ensures bot availability
2. **Cog Availability**: Checks ReminderCog loading status
3. **User Fetching**: Handles user object retrieval failures
4. **Time Parsing**: Validates time specification format
5. **Permission Checks**: Respects Discord permission requirements

**Error Scenarios:**
- Bot instance not available
- ReminderCog not loaded
- Invalid user ID
- User fetch failures
- Invalid time specification
- Permission denied errors
- Channel access issues

**Logging and Monitoring:**

**Operation Tracking:**
```python
logger.info(
    "Setting reminder",
    extra={
        "target_user_id": target_user_id,
        "guild": guild_id,
        "time_str": time_str
    },
)
logger.info("Reminder scheduled", extra={"result": result})
```

## Integration

The ReminderTools is used by:
- **ToolsFactory** for dynamic tool loading
- **LangChain agents** for scheduling capabilities
- **Orchestrator** for reminder functionality

## Dependencies

- `logging`: For operation monitoring
- `langchain_core.tools`: For tool integration
- `ReminderCog`: For reminder scheduling functionality
- `function.func`: For error reporting

## Usage Examples

**Basic Reminder:**
```python
# Set reminder for message author
result = await set_reminder("10m", "Meeting starts soon")
# Returns: "Reminder set for [user] in 10 minutes"
```

**Specific User:**
```python
# Set reminder for specific user
result = await set_reminder(
    time_str="2h",
    message="Your code review is ready",
    user_id=123456789012345678
)
# Returns: "Reminder scheduled for [user] in 2 hours"
```

**Complex Time:**
```python
# Tomorrow at specific time
result = await set_reminder(
    time_str="tomorrow 9am",
    message="Daily standup meeting"
)
# Returns: "Reminder set for tomorrow at 9:00 AM"
```

## Error Handling Examples

**Missing User:**
```python
# Invalid user ID
result = await set_reminder(
    time_str="1h",
    message="Test reminder",
    user_id=999999999999999999
)
# Returns: "Error: Failed to fetch user"
```

**Invalid Time:**
```python
# Malformed time string
result = await set_reminder(
    time_str="invalid time format",
    message="This will fail"
)
# Returns: "Error: Failed to parse time specification"
```

**Permission Issues:**
```python
# User without permissions
result = await set_reminder("1h", "Restricted reminder")
# Returns: "Error: Permission denied"
```

## Security Considerations

**User Privacy:**
- Respects user privacy settings
- Handles direct message permissions
- Validates user access rights

**Spam Prevention:**
- Rate limiting for reminder creation
- Guild-specific reminder limits
- Prevention of malicious reminder flooding

**Time Validation:**
- Sanitizes time specifications
- Prevents extremely long future dates
- Validates time format compatibility