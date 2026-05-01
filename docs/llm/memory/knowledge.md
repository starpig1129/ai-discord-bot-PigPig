# Knowledge Memory Provider

## Overview

The `KnowledgeMemoryProvider` handles "Shared Knowledge" at the server (Guild) or Channel level. This is used for storing community-specific information such as:
- **Server Rules**: Custom instructions for the bot within a specific guild.
- **Inside Jokes/Memes**: Information that applies to everyone in a channel.
- **Local Facts**: Information about a specific community or project.

## Levels of Knowledge

The provider fetches knowledge in a hierarchical manner:

1. **Guild Knowledge**: Broad instructions or facts applicable to the entire server.
2. **Channel Knowledge**: Specific context applicable only to the current channel.

## Implementation Details

### Hierarchical Fetching
The `get(guild_id, channel_id)` method fetches both levels simultaneously. Channel-level knowledge usually overrides or supplements Guild-level knowledge in the final prompt.

### Cache Management
- **TTL Cache**: Uses a standard time-to-live cache (default 5 minutes).
- **Invalidation**: Cache can be invalidated by administrative commands when knowledge is updated.

## Usage in Prompting

Knowledge is typically injected early in the system prompt to set the "ground rules" for the conversation within that specific environment.

---
*By separating User, Episodic, and Knowledge memory, the bot can distinguish between "what I know about you" vs "what I know about this place".*
