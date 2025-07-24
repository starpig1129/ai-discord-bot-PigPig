# GPT Core - Tool Executor

**File:** [`gpt/core/tool_executor.py`](gpt/core/tool_executor.py)

The `ToolExecutor` is a dedicated component responsible for running the tools that the `ActionDispatcher` decides to use. It acts as a bridge between the AI's intent (the action list) and the actual Python code that performs the action.

## `ToolExecutor` Class

### `__init__(self, bot)`

Initializes the executor with a reference to the bot instance and the global `tool_registry`.

### `async execute_tools(self, action_list: List[Dict], context: ToolExecutionContext) -> List[Dict]`

This is the main method of the class. It iterates through a list of tool calls (the `action_list` provided by the LLM) and executes them sequentially.

*   **Parameters:**
    *   `action_list` (List[Dict]): A list of dictionaries, where each dictionary represents a tool call with its `tool_name` and `parameters`.
    *   `context` (ToolExecutionContext): A data class that bundles together all the necessary contextual information for the tool to run, such as the `discord.Message` object, the bot instance, and a logger.
*   **Process:**
    1.  It loops through each action in the `action_list`.
    2.  It skips any action named `directly_answer`, as this is a signal to generate a text response, not run a tool.
    3.  It uses the `tool_name` to look up the corresponding tool object in the `tool_registry`.
    4.  It calls the `execute` method of the tool object, passing the `context` and unpacking the `parameters` dictionary as keyword arguments.
    5.  It takes the return value from the tool and passes it to `_format_tool_result`.
    6.  The formatted result is appended to a list.
*   **Returns:** A list of dictionaries, where each dictionary is a formatted tool result ready to be inserted back into the conversation history for the final response generation.

### `_format_tool_result(self, tool_name: str, result: Any) -> Dict[str, Any]`

This helper method takes the raw return value from a tool and formats it into the specific JSON structure required by the Gemini API for function calling.

*   **Structure:**
    ```json
    {
        "role": "function",
        "name": "tool_name",
        "content": "..."
    }
    ```
*   **Content Handling:** It intelligently handles different types of results. Dictionaries and lists are serialized to a JSON string, while other types are converted to a plain string.