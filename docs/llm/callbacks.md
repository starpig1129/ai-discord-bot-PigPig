# LLM Callbacks

## Overview

The `llm.callbacks` module implements custom LangChain callback handlers to provide real-time feedback to Discord users during complex AI reasoning and tool execution processes.

## `ToolFeedbackCallbackHandler`

This handler intercepts LangChain's internal tool execution events to update Discord messages, keeping users informed of the bot's background actions.

### Core Logic

When a tool starts execution (`on_tool_start`), the handler:
1. Identifies the tool name (e.g., `GoogleSearch`, `YouTubeSearch`).
2. Consults the `LanguageManager` to find the localized feedback message for that specific tool.
3. Falls back to a generic "Processing [Tool Name]..." message if no specific translation is found.
4. Uses `safe_edit_message` to update the bot's response in Discord with the status update.

### Resilience Features

- **Error Suppression**: Callback errors are caught and logged but never allowed to interrupt the primary AI reasoning process.
- **Async Safety**: Uses `asyncio.shield` to protect Discord message edits from being cancelled if the parent task is interrupted, preventing event loop mismatch errors.

## Integration

The callback handler is automatically instantiated and injected into the `Orchestrator`'s agent execution chain.

```python
# Example Internal usage
callbacks = [
    ToolFeedbackCallbackHandler(
        message_edit=message,
        language_manager=lang_manager,
        guild_id=guild_id
    )
]

# Passed to LangChain agent
await agent_executor.ainvoke(input, config={"callbacks": callbacks})
```

---
*By providing granular feedback, this system improves perceived performance and reduces user uncertainty during long-running AI tasks.*
