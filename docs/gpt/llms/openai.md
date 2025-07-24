# LLM Providers - OpenAI

**File:** [`gpt/llms/openai.py`](gpt/llms/openai.py)

This module provides a wrapper for interacting with the OpenAI API, specifically the GPT-4o and GPT-4o-mini models.

## `async generate_response(...)`

This function implements the standard interface for generating a response from the OpenAI API.

*   **Model Selection:** It dynamically selects the model to use. If any image input is provided, it automatically uses the more powerful `gpt-4o` model; otherwise, it defaults to the faster and more cost-effective `gpt-4o-mini`.
*   **Input Formatting:** It correctly formats the conversation history and system prompt into the `[{ "role": "system", "content": "..." }, { "role": "user", "content": "..." }]` structure required by the OpenAI API.
*   **Multi-modal Support:** It handles image inputs by converting them to base64 strings and embedding them in the user message content, following the format for the Vision API.
*   **Token Limit:** It includes a loop that checks the total number of tokens in the messages using `tiktoken`. If the token count exceeds the model's limit (127,000), it will progressively remove the oldest messages from the history until the context fits.
*   **Streaming:** It makes a streaming request to the API and yields the response chunks as they are received.
*   **Error Handling:** It catches common API errors (like invalid API key, rate limits, insufficient quota) and raises a specific `OpenAIError` with a user-friendly message, allowing the `ResponseGenerator` to gracefully fall back to another model.