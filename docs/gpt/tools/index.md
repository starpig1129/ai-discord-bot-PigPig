# Tool System

**Location:** [`gpt/tools/`](gpt/tools/)

The Tool System is a powerful and extensible framework that allows the bot's AI to perform actions beyond just generating text. It provides a structured way to define functions (tools) that the LLM can decide to call, execute them securely, and use their results to inform its final response.

## Core Components

*   **[Tool Registry](./registry.md):** The central singleton that manages all available tools.
*   **[Built-in Tools](./builtin/index.md):** The collection of predefined tools that the AI can use.

## The `@tool` Decorator

**File:** [`registry.py`](gpt/tools/registry.md)

The heart of the system is the `@tool` decorator. Any asynchronous function decorated with `@tool` is automatically parsed and registered as an available tool for the LLM.

*   **Automatic Schema Generation:** The decorator inspects the function's signature and docstring to automatically generate a schema.
    *   **`name`:** Taken from the function name.
    *   **`description`:** Taken from the first line of the function's docstring.
    *   **`parameters`:** Inferred from the function's arguments, their type hints, and their descriptions in the "Args:" section of the docstring (Google-style).

## `ToolExecutionContext`

**File:** [`tool_context.py`](gpt/tools/tool_context.md)

To avoid passing numerous arguments to every tool function, a `ToolExecutionContext` object is used. This simple data class bundles all necessary contextual information, such as the `bot` instance, the original `discord.Message`, and a logger. The first argument of any function decorated with `@tool` must be this context object.

## Execution Flow

1.  When the `ActionDispatcher` needs to decide on an action, it calls `tool_registry.get_tools_string_for_prompt()`.
2.  The **[Tool Registry](./registry.md)** provides a formatted string describing all registered tools, which is then included in the prompt sent to the LLM.
3.  The LLM analyzes the user's request and the list of tools and returns a JSON object specifying which tool(s) to call and with what parameters.
4.  The `ActionDispatcher` passes this JSON object to the **[Tool Executor](../core/tool_executor.md)**.
5.  The **Tool Executor** looks up the specified tool in the registry and calls its `execute` method, passing the `ToolExecutionContext` and the parameters.
6.  The tool function (e.g., `internet_search` in the built-in tools) runs its logic, often by calling a method in its corresponding Cog.
7.  The result is returned up the chain, formatted, and included in the final prompt to the LLM for generating a natural language response.