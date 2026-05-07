# File: `llm/memory/schema.py`

## Overview
Core logic and functionalities for schema.py. This file is part of the llm subsystem and handles the primary operations for its respective domain.

## Classes

### `UserInfo`
Information about a single user used by procedural memory.

- **Attributes**:
  - `user_background` (`Optional[str]`): Class attribute.
  - `procedural_memory` (`Dict[Tuple[str, Any]]`): Class attribute.
  - `last_updated` (`Optional[str]`): Class attribute.

### `ProceduralMemory`
Holds procedural memory for multiple users keyed by user_id.

- **Attributes**:
  - `user_info` (`Dict[Tuple[str, UserInfo]]`): Class attribute.

### `ShortTermMemory`
Stores recent messages; each message is a mapping containing at least author_id, author, content, timestamp (numeric UNIX seconds as float).

- **Attributes**:
  - `messages` (`List[Dict[Tuple[str, Any]]]`): Class attribute.

### `SystemContext`
Aggregated context used to build prompts for the LLM.

- **Attributes**:
  - `short_term_memory` (`ShortTermMemory`): Class attribute.
  - `procedural_memory` (`ProceduralMemory`): Class attribute.
  - `current_channel_name` (`str`): Class attribute.
  - `timestamp` (`float`): Class attribute.
