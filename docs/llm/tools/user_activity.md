# User Activity Tools

## Overview

The `UserActivityTools` class provides capabilities for the AI to observe current presence and activity patterns within Discord channels. Specifically, it allows the bot to "see" who else is present in the conversation, whether in a text channel or a voice channel.

## Class: UserActivityTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: A list containing the `get_channel_participants` tool.

### Tool: get_channel_participants

```python
@tool
def get_channel_participants() -> str:
```

**Returns:**
- `str`: A formatted list of users currently active or connected.

**Purpose:**
Identifies which users are likely "listening" or "available" in the current context.

**Features:**
- **Voice Channel Logic**: If called from a voice channel, it lists all currently connected members.
- **Text Channel Logic**: If called from a text channel, it lists online human members (excluding bots).
- **Status Indicators**: Shows online status (🟢), idle (🌙), or DND (⛔).
- **Device Awareness**: Shows if a user is connected via Mobile, Desktop, or Web.
- **Privacy Filtering**: Excludes offline users and bots from the participants list.

## Implementation Details

- **Device Detection**: Inspects `mobile_status`, `desktop_status`, and `web_status` attributes of Discord `Member` objects.
- **Sorting**: Prioritizes online members at the top of the list.
- **Throttling**: Limits the display to the top 20 active members to avoid prompt spam.
- **Target Mode**: Routed to the **Info Agent** (`target_agent_mode = "info"`).

## Usage Examples

**Checking the Room:**
```python
# Returns "## Active Users in 'general' (5 total) - 🟢 Alice [Desktop] - 🌙 Bob [Mobile]"
result = get_channel_participants()
```

## Performance & Constraints

- **Discord Intent Requirements**: Requires the "Presence Intent" and "Server Members Intent" to accurately detect status and device info.
- **Text Channel Accuracy**: In text channels, "active" is defined as being online with access to the channel, as Discord does not provide a real-time "viewing channel" list.

## Dependencies

- `discord.py`: For member status and device inspection.
