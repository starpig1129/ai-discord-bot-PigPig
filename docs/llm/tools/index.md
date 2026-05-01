# LLM Tools Architecture

## Overview

The PigPig Bot's LLM can interact with the world through a set of specialized **Tools**. These tools allow the AI to search the internet, manage reminders, perform complex math, and access the bot's internal memory systems.

## The Tool Layer

All tools are located in the `llm/tools/` directory. Each tool module typically exposes a `*Tools` class that acts as a container for one or more LangChain-compatible tools.

### `ToolsFactory`
The `ToolsFactory` (in `llm/tools_factory.py`) is responsible for:
1. **Discovery**: Dynamically finding tool classes in the `llm/tools/` package.
2. **Instantiation**: Injecting the `RuntimeContext` (bot instance, channel info, etc.) into the tools.
3. **Filtering**: Enabling or disabling tools based on the bot's configuration and guild permissions.

## Anatomy of a Tool

A typical tool module follows this pattern:

```python
class MyTools:
    def __init__(self, runtime):
        self.runtime = runtime

    def get_tools(self):
        @tool
        async def my_custom_tool(param: str) -> str:
            """Tool description used by LLM."""
            # Implementation
            return "result"
        return [my_custom_tool]
```

## Available Tool Categories

- **Information Retrieval**: Internet search, YouTube info, Wikipedia.
- **Internal Knowledge**: User stats, server context, memory retrieval.
- **Utility**: Math operations, reminders, image generation.
- **Meta-Tools**: `list_tools` for discovering other available tools.

---
*For a complete reference of available tools and their signatures, see the [Tool List](list.md).*