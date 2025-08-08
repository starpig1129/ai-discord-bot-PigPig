# GPT Core - Message Sender & Context Builders

**File:** [`gpt/core/message_sender.py`](gpt/core/message_sender.py)

This module contains a collection of high-level helper functions that are used by the `ActionDispatcher` to assemble the final prompt and generate the bot's natural language response after all tool actions have been completed.

## Main Function

### `async gpt_message(message_to_edit, message, original_prompt, history_dict, image_data)`

This function is the final step in the response pipeline before sending the text to the user.

*   **Process:**
    1.  It takes the complete, final conversation history, which now includes the results from any tools that were executed.
    2.  It retrieves the effective system prompt for the channel using `get_system_prompt`.
    3.  It calls the low-level `generate_response` function to get the final, streamed, natural language response from the LLM.
    4.  It handles the streaming response, editing the bot's "Thinking..." message in real-time as the response is generated.
    5.  It processes any `<tenor>` tags in the final response to send GIFs.
*   **Returns:** The final, complete text response from the AI.

## Context Building Functions

These functions are responsible for gathering and formatting the contextual information that is fed into the LLM prompts.

### `async build_intelligent_context(...)`

This function constructs the "intelligent context" by gathering information about the current state of the conversation.

1.  It extracts the IDs of all users participating in the recent conversation.
2.  It calls the `UserManager` to retrieve stored data and profiles for these users.
3.  It calls `search_relevant_memory` to find relevant past conversation segments.
4.  It uses the `StructuredContextBuilder` to format all this information into a clean, readable block of text.
5.  Finally, it wraps this text in the Gemini API's standard "function call" format using `format_intelligent_context`.

### `async search_relevant_memory(...)`

A wrapper around the `MemoryManager`'s search functionality. It performs a hybrid search based on the user's prompt to find relevant past conversations.

### Formatting Helpers

*   **`format_intelligent_context(...)`:** Formats the context string into the `{"role": "function", "name": "memory_search", ...}` structure.
*   **`format_memory_context_structured(...)`:** Formats the raw memory search results into the `{"role": "function", "name": "memory_retrieval", ...}` structure.

## System Prompt Management

### `get_system_prompt(...)`

This function is the primary entry point for retrieving the correct system prompt. It orchestrates the three-tiered inheritance model by first attempting to get a custom prompt from the `SystemPromptManagerCog` and, if that fails or is not configured, falling back to the legacy YAML-based `PromptManager`.