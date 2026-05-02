# Server Context Tools

## Overview

The `ServerContextTools` class provides a suite of tools that allow the AI agent to inspect its surroundings within Discord. These tools provide real-time information about the current server (guild), specific channels, and individual user profiles, including their current activities and roles.

## Class: ServerContextTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: A list containing `get_server_context`, `get_channel_context`, and `get_user_discord_info`.

### Tools Reference

#### `get_server_context`
- **Description**: Queries basic information about the current Discord server.
- **Returns**: Server name, ID, member count, boost level, owner, top roles (up to 20), and text/voice channels (up to 25).
- **Purpose**: Gives the bot an "environmental" awareness of where it is.

#### `get_channel_context(channel_name: Optional[str])`
- **Description**: Queries detailed info about a specific channel.
- **Args**:
  - `channel_name`: Optional name of a channel to inspect. Defaults to current channel.
- **Returns**: Channel category, topic, NSFW status, slowmode settings, and online member count.
- **Purpose**: Understands specific rules or themes of a channel.

#### `get_user_discord_info(user_id: Optional[str])`
- **Description**: Queries a member's Discord profile and real-time activity.
- **Args**:
  - `user_id`: Discord ID or @mention. Defaults to message sender.
- **Returns**: Join date, account age, nickname, roles, status (Online/Idle/DND), and detailed activities (Spotify, Games, Custom Status with duration).
- **Purpose**: Personalized interaction based on what the user is currently doing.

## Implementation Details

- **Activity Tracking**: Uses a sophisticated duration helper to show how long a user has been playing a game or listening to Spotify.
- **Mentions Parsing**: Correctly handles `<@123>` and `<@!123>` mention formats for user lookups.
- **Privacy Awareness**: Only shows online member counts and public profile data available to the bot's permission level.
- **Target Mode**: Routed to the **Info Agent** (`target_agent_mode = "info"`).

## Usage Examples

**Checking the Server:**
```python
# Returns server overview
result = await get_server_context()
```

**Inspecting a User's Status:**
```python
# Returns "Playing: Elden Ring (for 2h 15m)"
result = await get_user_discord_info(user_id="123456789")
```

## Performance & Constraints

- **Discord API Latency**: These tools involve active calls to the Discord gateway; results are not cached to ensure real-time accuracy.
- **Truncation**: Role and channel lists are truncated to prevent overloading the LLM's context window.
- **Permissions**: Requires "Server Members Intent" and "Presence Intent" to be enabled in the Discord Developer Portal.

## Dependencies

- `discord.py`: For all Discord API interactions.
- `datetime`: For calculating activity durations.
