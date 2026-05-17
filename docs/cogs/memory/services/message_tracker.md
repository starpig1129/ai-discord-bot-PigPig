# File: `cogs/memory/services/message_tracker.py`

## Overview
Core logic and functionalities for message_tracker.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `MessageTracker`
Tracks new messages in channels for the memory system.

- **Attributes**:
  - `bot` (`Any`): Instance attribute.
  - `storage` (`Any`): Instance attribute.
  - `settings` (`Any`): Instance attribute.
  - `_pending_message_count` (`Any`): Instance attribute.
  - `_processing_tasks` (`Any`): Instance attribute.
  - `_processing_semaphore` (`Any`): Instance attribute.
  - `_active_summarization_task` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(bot: Bot, storage: StorageInterface, settings: MemoryConfig) -> Any`: Initializes the MessageTracker.
  - `track_message(message: discord.Message) -> Any`: Tracks a message, adding it to the pending list if it's not from a bot
  - `_schedule_processing(channel: discord.TextChannel) -> Any`: Schedules channel memory processing with a debounce delay.
  - `interrupt_all() -> Any`: Interrupts all pending and active memory processing tasks.
  - `_process_channel_memory(channel: discord.TextChannel) -> Any`: Processes memory for a channel when threshold is reached.
  - `get_pending_count() -> int`: Gets the current count of pending messages.
  - `reset_pending_count() -> Any`: Resets the pending message count to zero.

## Functions

### `discord_id_to_unix_timestamp(message_id: int) -> float`
Convert Discord message ID to Unix timestamp in milliseconds. Plays a key role in the system logic.
