# Discord Interaction Tools

## Overview

The `DiscordInteractionTools` class provides advanced interaction capabilities beyond simple text responses. These tools allow the LLM to manage reactions, use custom server emojis, send stickers, change its local identity, and manipulate the conversational flow with timing and message retraction.

## Class: DiscordInteractionTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

**Parameters:**
- `runtime`: Orchestrator request containing bot, message, and logger.

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: A list containing all interaction tools.

### Tools Reference

#### `get_guild_emojis`
- **Description**: Retrieves a list of custom emojis available in the current server.
- **Purpose**: Helps the agent select relevant server-specific emojis for its response.

#### `add_reaction(emoji: str, message_id: Optional[str])`
- **Description**: Adds an emoji reaction to a message.
- **Args**:
  - `emoji`: Unicode (👍) or custom emoji name (pig_smile).
  - `message_id`: Optional ID of a past message to react to.
- **Purpose**: Non-verbal communication and acknowledgment.

#### `get_guild_stickers`
- **Description**: Lists stickers available in the current server.
- **Purpose**: Discovery of server-specific graphical assets.

#### `send_sticker(sticker_id: str)`
- **Description**: Sends a standalone sticker message.
- **Note**: Stickers are sent as separate messages and do not count as part of the text stream.

#### `change_own_nickname(new_nickname: str)`
- **Description**: Changes the bot's nickname in the current server.
- **Purpose**: Dynamic roleplay or mood adjustment (e.g., "Detective PigPig").

#### `delete_own_last_message`
- **Description**: Deletes the bot's most recent message in the channel.
- **Purpose**: Self-correction, dramatic effects, or "retracting" statements.

#### `dramatic_pause(seconds: int)`
- **Description**: Pauses the response stream (max 10s) while maintaining the "typing..." indicator.
- **Purpose**: Comedic timing, suspense, or simulating "thinking."

## Implementation Details

- **Target Message Resolution**: Uses a smart helper `_get_target_message` to resolve message IDs from the channel history if provided.
- **Emoji Resolution**: Automatically matches string names to server-specific emoji objects.
- **Permission Handling**: Includes robust error handling for `Forbidden` (lacking Discord permissions) and `NotFound` scenarios.
- **Target Mode**: Typically routed to the **Message Agent** (`target_agent_mode = "message"`).

## Usage Examples

**Dynamic Persona:**
```python
# Change name and pause for effect
await change_own_nickname("PigPig Investigates")
await dramatic_pause(3)
```

**Reactions:**
```python
# React to a past message (found via memory)
await add_reaction(emoji="✅", message_id="123456789")
```

## Performance & Constraints

- **Rate Limits**: Excessive use of `add_reaction` or `change_own_nickname` may trigger Discord rate limits.
- **History Scanning**: `delete_own_last_message` scans the last 20 messages to find the bot's own post.
- **Sticker Sending**: Sending a sticker is a blocking network call that initiates a new Discord message.

## Dependencies

- `discord.py`: Core API interaction.
- `asyncio`: For handling dramatic pauses.
