# User Stats Tools

## Overview

The `UserStatsTools` class provides tools for the AI agent to retrieve and visualize user activity patterns within a Discord server. It can generate both a structured text "card" for immediate conversational use and a rich graphical PNG image containing a word cloud and activity charts.

## Class: UserStatsTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: A list containing the `get_user_stats` tool.

### Tool: get_user_stats

```python
@tool
async def get_user_stats(user_id: Optional[str] = None) -> str:
```

**Parameters:**
- `user_id`: Optional Discord user ID. Defaults to the message author.

**Returns:**
- `str`: A concise text summary (card) of the user's statistics.

**Side Effects:**
- Sends a **PNG image** to the Discord channel as a file attachment.

**Purpose:**
Provides a comprehensive overview of a user's engagement, including message frequency, peak hours, most used words, and server-specific emojis.

**Features:**
- **Text Card**: A localized summary showing total messages, peak activity periods, current message streak, and top channels.
- **Graphical Dashboard (PNG)**:
  - **Word Cloud**: Visualizes the most frequently used words (with CJK font support).
  - **Activity Chart**: A 24-hour bar chart showing the user's most active times.
  - **Channel Distribution**: Mini-progress bars showing the percentage of messages across different channels.
  - **Emoji Ranking**: Lists the user's favorite reactions and emojis.
- **Localization**: Fully integrates with the bot's `LanguageManager` for multi-language support (defaulting to Traditional Chinese fallbacks).
- **Theming**: Uses the "Catppuccin Mocha" color palette for a professional, dark-mode aesthetic.

## Implementation Details

- **Word Cloud Generation**: Uses the `wordcloud` and `Pillow` libraries to generate a 800x640 dashboard.
- **CJK Font Support**: Automatically searches for Noto Sans CJK fonts to ensure proper rendering of Chinese, Japanese, and Korean characters.
- **StatsStorage**: Interfaces with the `StatsCog` to retrieve aggregated data from the bot's analytics database.
- **Executor Offloading**: Image generation is performed in a separate thread (via `run_in_executor`) to prevent blocking the async event loop.
- **Target Mode**: Routed to the **Info Agent** (`target_agent_mode = "info"`).

## Usage Examples

**Self-Check:**
```python
# User: "How am I doing in this server?"
# Bot: Returns text summary and uploads a PNG dashboard.
result = await get_user_stats()
```

**Checking Another User:**
```python
# User: "What are @User's stats?"
result = await get_user_stats(user_id="123456789")
```

## Performance & Constraints

- **Generation Time**: Creating the PNG and word cloud typically takes 1-3 seconds.
- **Data Availability**: Statistics are only available if the `StatsCog` has been actively tracking the user in the server.
- **Font Dependency**: Requires CJK fonts to be installed on the host system for proper non-English word cloud rendering.

## Dependencies

- `wordcloud`: For generating the frequency-based word visualization.
- `PIL (Pillow)`: For drawing the dashboard and charts.
- `StatsCog`: The source of truth for message and activity data.
- `LanguageManager`: For localized labels and card headers.
