# Knowledge Management Tools

## Overview

The `KnowledgeTools` class provides tools for the LLM to manage shared context and cultural facts at the Guild (Server) and Channel levels. Unlike episodic memory (which is raw history), knowledge tools are used to store "distilled" information like inside jokes, relationship statuses, aliases, and channel-specific rules.

## Class: KnowledgeTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

**Parameters:**
- `runtime`: Orchestrator request containing bot, message, and logger.

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: A list containing `update_guild_knowledge` and `update_channel_knowledge`.

### Tools Reference

#### `update_guild_knowledge(new_information: str, category: str)`
- **Description**: Records or updates facts, memes, or culture for the ENTIRE SERVER.
- **Args**:
  - `new_information`: The new fact or update to record.
  - `category`: One of `inside_joke`, `relationship`, `alias`, `special_event`, or `general`.
- **Purpose**: Permanent storage of server-wide context.

#### `update_channel_knowledge(new_information: str, category: str)`
- **Description**: Records or updates facts or rules for the CURRENT CHANNEL only.
- **Args**:
  - `new_information`: The information to record.
  - `category`: Category of information.
- **Purpose**: Localized context for specific channels (e.g., "The Spam Corner" rules).

## Data Flow

1. **Discovery**: The agent identifies a new fact (e.g., "User A and User B are now rivals").
2. **Execution**: The agent calls `update_guild_knowledge`.
3. **Persistence**: The tool calls `UserDataCog._save_knowledge_data`.
4. **Integration**: The stored knowledge is injected into the **System Prompt** in future interactions within that guild/channel.

## Implementation Details

- **Backend Integration**: Reliant on the `UserDataCog` for database operations.
- **Context Injection**: Knowledge updated via these tools is automatically prioritized in the LLM's long-term retrieval system.
- **Validation**: Categories are standardized to ensure consistent categorization in the knowledge base.
- **Target Mode**: Typically routed to the **Message Agent** (`target_agent_mode = "message"`) as it involves a "write" action.

## Usage Examples

**Recording a Meme:**
```python
# Server-wide meme
await update_guild_knowledge(
    new_information="Whenever someone says 'Hello', we all reply with 'o/'",
    category="inside_joke"
)
```

**Recording an Alias:**
```python
# Channel-specific nickname
await update_channel_knowledge(
    new_information="User123 is the 'King of Slimes' here",
    category="alias"
)
```

## Performance & Constraints

- **Storage**: Knowledge is stored as structured records in the bot's persistence layer (SQL/NoSQL).
- **Retrieval**: Unlike vector search, knowledge is usually injected as "Shared Context" into the top of the prompt.
- **Limits**: Individual knowledge entries should be concise to maintain prompt efficiency.

## Dependencies

- `cogs.user_data.UserDataCog`: Handle for the underlying persistence system.
- `langchain_core.tools.BaseTool`: Core tool wrapper.
