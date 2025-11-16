# Procedural Memory Provider

## Overview

The `ProceduralMemoryProvider` is responsible for providing procedural memory for multiple users in the LLM system. It fetches user information from a SQLite database and returns structured procedural memory data.

## Class: ProceduralMemoryProvider

### Constructor

```python
def __init__(self, user_manager: SQLiteUserManager):
```

**Parameters:**
- `user_manager`: An instance of `SQLiteUserManager` for database operations

**Description:**
Initializes the provider with a user manager instance for database access.

### Methods

#### `async def get(self, user_ids: List[str]) -> ProceduralMemory`

**Parameters:**
- `user_ids`: List of user ID strings to fetch information for

**Returns:**
- `ProceduralMemory`: A data structure containing user information mapping

**Description:**
Fetches procedural memory for a list of user IDs. The method uses the user manager's batch method to efficiently retrieve multiple users' information. Any errors during retrieval are reported and handled gracefully by returning an empty mapping.

**Error Handling:**
- Any exceptions during user retrieval are reported using `func.report_error()`
- Returns empty user_info dict on failure to maintain system resilience

**Implementation Details:**
```python
# Uses batch method for efficient database operations
users: Dict[str, UserInfo] = await self.user_manager.get_multiple_users(
    [str(uid) for uid in user_ids]
)
```

## Integration

This provider is used by the `ContextManager` to build procedural memory context for LLM prompts. It connects the user data from the SQLite database to the LLM system's memory architecture.

## Dependencies

- `llm.memory.schema.ProceduralMemory`
- `llm.memory.schema.UserInfo`
- `cogs.memory.users.manager.SQLiteUserManager`
- `function.func` (for error reporting)