# Procedural Memory Provider

## Overview

The `ProceduralMemoryProvider` manages user-specific behavioral data. Unlike Episodic memory (which is about *what happened*), Procedural memory is about *who the user is* and *how the bot should interact with them*.

## Functionality

The provider fetches `UserInfo` from the `SQLiteUserManager`. This data typically includes:
- **User Bio**: A short description of the user.
- **Interests**: Topics the user cares about.
- **Custom Instructions**: Specific rules the user has set for the bot's behavior towards them.
- **Interaction History**: High-level summaries of past interactions.

## Technical Implementation

### TTL Cache
To avoid hitting the SQLite database for every single message, the provider uses a per-user cache:
- **Logic**: Each `user_id` is cached with its own expiration timer.
- **Invalidation**: The `invalidate(user_id)` method is called by the `/memory save` command to ensure that updates are reflected immediately.

### Batch Fetching
The provider supports `get_multiple_users()`, allowing it to fetch context for everyone involved in a multi-user conversation in a single pass.

## Schema: `UserInfo`

The data is structured using Pydantic models (defined in `llm.memory.schema`):
- `user_id`: Discord ID.
- `nickname`: User's display name.
- `bio`: Extracted or user-provided biography.
- `instructions`: Custom behavioral overrides.

## Integration

The result is injected into the prompt as a dedicated section:
```text
--- User Profiles ---
User: Alice
Bio: Loves coding and cats.
Instructions: Always be polite.
---
```

---
*Procedural memory is the foundation of the bot's personalized interaction model, allowing it to adapt its tone and knowledge to each individual user.*