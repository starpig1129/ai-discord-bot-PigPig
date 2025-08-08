# GPT Core - Action Dispatcher

**File:** [`gpt/core/action_dispatcher.py`](gpt/core/action_dispatcher.py)

The `ActionDispatcher` is the primary decision-making component in the AI pipeline. It receives a user's prompt, gathers all necessary context, and then decides on the most appropriate course of action—either by selecting one or more tools to execute or by deciding to answer directly.

## `ActionDispatcher` Class

### `__init__(self, bot)`

Initializes the dispatcher with a reference to the bot instance, the `tool_registry`, and an instance of the `ToolExecutor`.

### `async choose_act(self, prompt, message, ...)`

This is the main entry point for the dispatcher. It orchestrates the entire pre-processing and decision-making workflow.

*   **Process:**
    1.  **Context Gathering:** It asynchronously gathers multiple streams of context in parallel:
        *   It processes any attachments (images, etc.) in the current message and recent history.
        *   It builds the `intelligent_context` by fetching user data and relevant memories.
        *   It constructs the recent `dialogue_history`.
    2.  **Context Assembly:** It combines the memory context, intelligent context, and dialogue history into a final, comprehensive history list that will be sent to the LLM.
    3.  **Action Selection:** It calls `_get_action_list` to determine the next steps.
    4.  **Action Execution:** It returns an `execute_action` asynchronous function. This function, when called by the `MessageHandler`, will run the `ToolExecutor` with the selected actions and then generate the final text response.

### Action Selection Logic (`_get_action_list`)

This method contains the logic for deciding what to do next.

1.  **Rule-based Routing:** It first checks the user's prompt against a list of simple regular expressions (`_rule_based_router`). This is a lightweight, fast path for common and unambiguous tool uses (e.g., if the message contains "calculate", it immediately routes to the `math` tool).
2.  **LLM-based Routing:** If no rule matches, it proceeds to the more powerful LLM-based routing.
    *   It retrieves the complete list of available tools and their descriptions from the `tool_registry`.
    *   It constructs a system prompt that instructs the LLM to act as a tool-selection expert and to respond with a JSON array of tool calls.
    *   It calls `generate_response` with this prompt and the full conversational context.
    *   It parses the JSON response from the LLM to get the list of actions.
3.  **Fallback:** If the LLM fails to produce valid JSON or an error occurs, it defaults to a safe action: `[{"tool_name": "directly_answer", "parameters": {"prompt": prompt}}]`, which tells the pipeline to simply generate a text response without using any tools.