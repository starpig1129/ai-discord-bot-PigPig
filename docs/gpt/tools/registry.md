# Tool System - Registry & Context

**Files:**
*   [`gpt/tools/registry.py`](gpt/tools/registry.py)
*   [`gpt/tools/tool_context.py`](gpt/tools/tool_context.py)

These files define the core infrastructure of the tool system: the registry that manages all tools and the context object that provides them with necessary resources.

## `ToolRegistry` Class

The `ToolRegistry` is a singleton class that serves as the central repository for all available tools.

*   **`register(self, tool: Tool)`:** The method used by the `@tool` decorator to add a new tool to the registry.
*   **`get_tool(self, name: str) -> Tool`:** Retrieves a tool by its name. This is used by the `ToolExecutor`.
*   **`get_tools_string_for_prompt(self) -> str`:** This is a key method for the AI. It generates a formatted string that describes all registered tools, including their names, descriptions, and parameters. This string is injected into the prompt to let the LLM know what tools it can choose from. The result is cached for efficiency.

## The `@tool` Decorator

This decorator is the primary way to create and register a new tool.

*   **Functionality:** It wraps an asynchronous function and automatically extracts its metadata to create a `Tool` object.
    *   **Name:** From the function's name (e.g., `async def my_tool(...)` becomes a tool named `my_tool`).
    *   **Description:** From the first line of the function's docstring.
    *   **Parameters:** It inspects the function's arguments, using their names, type hints, and descriptions from the Google-style docstring to create a list of `ToolParameter` objects.
*   **Registration:** After creating the `Tool` object, it automatically calls `tool_registry.register()` to make the tool available to the system.

## `ToolExecutionContext` Data Class

This is a simple data class that acts as a container for all the contextual information a tool might need to execute.

*   **Purpose:** Instead of passing many different arguments to every tool function, this single context object is passed as the first argument. This simplifies the tool function signatures and makes the system easier to maintain.
*   **Attributes:**
    *   `bot`: The main bot instance.
    *   `message`: The original `discord.Message` that triggered the tool call.
    *   `message_to_edit`: The bot's "Thinking..." message, which can be edited by the tool.
    *   `logger`: A logger instance for logging tool-specific information.