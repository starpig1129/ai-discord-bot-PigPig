# GPT Core System

**Location:** [`gpt/core/`](gpt/core/)

The GPT Core system is the central nervous system of the bot's AI capabilities. It defines the entire pipeline for processing a user's message, deciding on a course of action, executing tools, and generating a final, context-aware response.

## Core Components

The system is a collection of specialized modules that handle distinct stages of the response pipeline:

*   **[Message Handler](./message_handler.md):** The highest-level orchestrator, triggered by new Discord messages.
*   **[Action Dispatcher](./action_dispatcher.md):** The decision-making component that decides whether to use a tool or answer directly.
*   **[Tool Executor](./tool_executor.md):** The component responsible for executing the tools chosen by the Action Dispatcher.
*   **[Message Sender](./message_sender.md):** A collection of helper functions for building context and generating the final natural language response.
*   **[Response Generator](./response_generator.md):** The lowest-level component that directly interfaces with various Large Language Models (LLMs).

## Response Generation Pipeline

When a user mentions the bot, the following sequence of events occurs:

1.  The `on_message` event in `bot.py` calls the **[Message Handler](./message_handler.md)**.
2.  The **Message Handler** checks permissions and other prerequisites. If the message is a standard query, it invokes the **[Action Dispatcher](./action_dispatcher.md)**.
3.  The **Action Dispatcher** builds a comprehensive context for the message, incorporating recent conversation history, long-term memories from the Memory System, and user data.
4.  The **Action Dispatcher** then decides on the next step. It first checks a set of simple rules. If no rule matches, it calls an LLM with a list of available tools to get a structured list of actions (e.g., `[{"tool_name": "internet_search", "parameters": ...}]`).
5.  This action list is passed to the **[Tool Executor](./tool_executor.md)**.
6.  The **Tool Executor** runs each specified tool and collects the results.
7.  The results from the tools are formatted and added back into the conversation history.
8.  Finally, the **[Message Sender](./message_sender.md)** takes the complete conversation history (including the tool results) and calls the **[Response Generator](./response_generator.md)**.
9.  The **Response Generator** sends the final prompt to an LLM (like Gemini or a local model) to generate the natural language response that is sent back to the user.