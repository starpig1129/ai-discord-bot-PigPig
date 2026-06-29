# File: `llm/utils/safe_typing.py`

## Overview
Part of the LLM pipeline subsystem. Handles operations related to `safe_typing.py`. This module is responsible for orchestrating LLM interactions and processing.

## Classes

### `SafeTyping`
Typing indicator that handles per-channel deduplication and rate-limiting.

This class ensures that only one typing heart-beat loop is running per channel,
even if multiple tasks are processing messages for the same channel.
It also enforces a minimum interval between trigger_typing() calls and
handles 429 rate limits gracefully.

- **Attributes**:
  - `_sessions` (`Dict[int, int]`): Public attribute
  - `_tasks` (`Dict[int, asyncio.Task]`): Public attribute
  - `_last_trigger` (`Dict[int, float]`): Public attribute

- **Methods**:
  - `__init__(channel) -> None`: Initializes the instance.

## Functions

No module-level functions defined in this file.
