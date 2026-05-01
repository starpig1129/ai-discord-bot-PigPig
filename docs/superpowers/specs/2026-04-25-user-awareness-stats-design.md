# Design: User Awareness & Interaction Statistics

**Date:** 2026-04-25  
**Status:** Confirmed, pending implementation

## Context

Currently, PigPig bot's LLM agent lacks awareness of the following information:
1. Discord server structure (roles, channel lists, boost level, etc.)
2. Specific user information within the server (join date, roles, nickname)
3. Cumulative user behavior statistics (message count, active hours, common words)

The goal is to allow the bot to **autonomously judge** when this information is needed and retrieve it, making conversations more personalized and context-aware. It should also be able to present user statistics in text or image card formats.

Available assets:
- Large number of existing NDJSON log files (`logs/{guild_id}/{YYYYMMDD}/info.jsonl`), each record containing `user_id`, `channel_or_file`, `timestamp`, `action`, `message`
- Existing SQLite DB (`cogs/memory/db/`) where new tables can be added
- Tool discovery mechanism (`llm/tools_factory.py`) supporting new tool modules

---

## Architecture Overview

```
New DB Tables
  user_stats           ← Updated in real-time via on_message (new messages)
  log_migration_state  ← Background log parsing progress tracking (historical migration)

New Cog
  cogs/stats_cog.py    ← on_message listener + background log migration schedule

New Tools (llm/tools/)
  server_context.py    ← 3 tools: Query server/channel/user Discord info
  user_stats.py        ← 2 tools: Text stats card (for AI) / Image stats card (for users)

New Dependencies
  jieba                ← Chinese word segmentation (for top_words analysis)
  wordcloud            ← Generate word cloud images
```

---

## 1. DB Schema

Modified file: `cogs/memory/db/schema.py`

Add two SQLite tables:

```sql
-- Cumulative user statistics (calculated independently across servers)
CREATE TABLE IF NOT EXISTS user_stats (
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    total_messages INTEGER NOT NULL DEFAULT 0,
    active_hours TEXT NOT NULL DEFAULT '{}',
        -- JSON object, key is hour (0-23), value is message count
        -- Example: {"14": 45, "22": 30, "0": 12}
    top_channels TEXT NOT NULL DEFAULT '{}',
        -- JSON object, key is channel name, value is message count
    top_emojis TEXT NOT NULL DEFAULT '{}',
        -- JSON object, key is emoji character, value is count
    top_words TEXT NOT NULL DEFAULT '{}',
        -- JSON object, key is word, value is count (jieba segmentation)
    streak_days INTEGER NOT NULL DEFAULT 0,
        -- Current consecutive active days
    streak_last_date TEXT,
        -- "YYYY-MM-DD" format, used to calculate streaks
    last_active_at DATETIME,
    first_message_at DATETIME,
    PRIMARY KEY (user_id, guild_id)
);

-- Log migration progress tracking (to prevent duplicate processing)
CREATE TABLE IF NOT EXISTS log_migration_state (
    guild_id TEXT PRIMARY KEY,
    last_processed_date TEXT NOT NULL
        -- "YYYYMMDD" format, e.g., "20260424"
);
```

---

## 2. New Cog: `cogs/stats_cog.py`

**Responsibilities:**
1. `on_message` event listener: Update `user_stats` in real-time for every new message.
2. Background log migration task on startup (process historical data).

**StatsStorage Class** (embedded in cog or standalone in `cogs/memory/db/stats_storage.py`):
- `get_user_stats(user_id, guild_id)` → dict
- `update_user_stats(user_id, guild_id, message_content, channel_name, timestamp)` → None
  - Increment `total_messages + 1`
  - Increment `active_hours[hour] + 1`
  - Increment `top_channels[channel_name] + 1`
  - Parse emojis and update `top_emojis`
  - Update `top_words` after jieba segmentation (filter stop words, keep top 200 words)
  - Calculate and update `streak_days`
  - Update `last_active_at`, set `first_message_at` if empty
- `get_migration_state(guild_id)` → Optional[str] (last_processed_date)
- `set_migration_state(guild_id, date_str)` → None

**Background Log Migration Task:**
```
Asynchronous background task (low-priority, processes one day at a time)
1. Read logs/ directory, find all guild_id subdirectories
2. For each guild:
   a. Read last_processed_date from log_migration_state
   b. Find unprocessed date directories (sorted ascending by date)
   c. For each date:
      - Open info.jsonl
      - Read line by line, filter action == "receive_message"
      - Call update_user_stats every 500 records (batch commit)
      - await asyncio.sleep(0) (yield event loop to avoid blocking)
      - Update log_migration_state after completion
   d. sleep(30) after processing each day before continuing to the next
3. Log completion and end task
```

**Performance Considerations:**
- Process line by line when reading NDJSON, do not load the whole file.
- Batch commit every 500 records to reduce write frequency.
- sleep(30) between days to avoid I/O contention.
- jieba segmentation only processes Chinese and English words, filters words with length < 2 and pure numbers.

---

## 3. New Tools: `llm/tools/server_context.py`

**agent_mode:** `"info"` (used by info_agent to get context during analysis)

**Tool List:**

### 3.1 `get_server_context`
Queries basic information about the current Discord server.
- No parameters (guild retrieved from runtime)
- Return format (text):
  ```
  Server: xxx (ID: 123)
  Members: 245
  Boost Level: Level 2 (15 boosts)
  Roles (10): Admin, VIP, Member...
  Text Channels (8): announcement, chat, music...
  ```

### 3.2 `get_channel_context`
Queries detailed information about a specific channel.
- Parameters: `channel_name: Optional[str]` (defaults to current channel)
- Returns: Channel topic, category, current online users (or connected users for voice channels)

### 3.3 `get_user_discord_info`
Queries Discord data for a specific member in the server.
- Parameters: `user_id: Optional[str]` (defaults to message sender)
- Returns: Join date, owned roles, server nickname, current activity status

---

## 4. New Tools: `llm/tools/user_stats.py`

**agent_mode:** `"info"` (used by info_agent)

### 4.1 `get_user_stats_card`
Text-formatted statistics card for AI to naturally embed in conversation responses.
- Parameters: `user_id: Optional[str]` (defaults to message sender)
- Return format (text):
  ```
  📊 Statistics for xxx
  ────────────
  Total Messages: 1,247
  Peak Activity: 10-11 PM (342 messages)
  Activity Streak: 7 days
  Most Active Channel: chat (55%)
  Top Words: hahaha, speechless, dying, OK
  Favorite Emojis: 😂 × 142, 👍 × 98
  First Message: 2025-12-01 (145 days ago)
  ```

### 4.2 `get_user_stats_image`
Generates a PNG statistics image with a word cloud and sends it to the Discord channel as an attachment.
- Parameters: `user_id: Optional[str]` (defaults to message sender)
- Uses `wordcloud` library for word cloud, `Pillow` to compose the full stats image.
- Requires Chinese font (prefer system NotoSansCJK or included fallback font).
- Image content:
  - Top: Username, avatar thumbnail, basic stats (total messages, streak days)
  - Middle: Word cloud (weighted by top_words)
  - Bottom: Favorite emojis bar, activity hours histogram
- Returns: Confirmation text (image sent as `discord.File` attachment)

---

## 5. Dependencies

Added to `requirements.txt`:
```
jieba>=0.42.1
wordcloud>=1.9.3
```

(`Pillow` is already present, no need to add)

---

## 6. Modified Existing Files

| File | Modification |
|------|---------|
| `cogs/memory/db/schema.py` | Add SQL for creating `user_stats` and `log_migration_state` tables |
| `bot.py` | Load `stats_cog` in `setup_hook()` (same mechanism as other cogs) |
| `requirements.txt` | Add jieba, wordcloud |

---

## 7. New Files

| File | Description |
|------|------|
| `cogs/stats_cog.py` | StatsCog: on_message listener + background log migration |
| `cogs/memory/db/stats_storage.py` | StatsStorage: DB operations for user_stats and log_migration_state |
| `llm/tools/server_context.py` | 3 tools for server/channel/user info queries |
| `llm/tools/user_stats.py` | 2 statistics tools (text card + image card) |

---

## 8. Data Flow

```
Discord Message → bot.on_message()
  → StatsCog.on_message()
      → StatsStorage.update_user_stats()  [Real-time update]

User Question → info_agent
  → get_user_discord_info()               [Discord API query]
  → get_user_stats_card()                 [Read user_stats table]
  → get_server_context()                  [Discord API query]
  Results passed to message_agent → Generate personalized response

User requests stats card → info_agent
  → get_user_stats_image()
      → Read user_stats
      → jieba segmentation (uses existing top_words, no real-time segmentation needed)
      → wordcloud generation
      → Pillow image composition
      → message.channel.send(file=discord.File(image))
  → message_agent replies "Stats image sent"

Bot Startup → StatsCog background task
  → Read logs/{guild_id}/{YYYYMMDD}/info.jsonl day by day
  → Filter receive_message, batch update user_stats
  → sleep(30) between days, record progress in log_migration_state
```

---

## 9. Verification Plan

1. **Unit:** Verify `StatsStorage.update_user_stats()` correctly updates JSON fields (active_hours, top_channels, etc.).
2. **Integration:** Start bot, send messages, check SQLite for `user_stats` data.
3. **Tool Call:** Ask the bot "show my stats in this server", verify AI calls `get_user_stats_card`.
4. **Image Generation:** Ask the bot "generate my stats card", verify Discord channel receives image attachment.
5. **Log Migration:** Verify background task logs progress and updates `log_migration_state` table.
6. **Server Query:** Ask the bot "how many people are in this server?", verify AI calls `get_server_context`.
