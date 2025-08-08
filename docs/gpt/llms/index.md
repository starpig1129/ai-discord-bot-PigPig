# LLM Providers

**Location:** [`gpt/llms/`](gpt/llms/)

This directory contains the abstraction layer for interacting with various third-party and local Large Language Models (LLMs). Each module in this directory acts as a standardized wrapper, providing a consistent `generate_response` function that the main `ResponseGenerator` can call. This design decouples the core logic from the specific implementation details of each LLM API.

## Standardized Interface

Each provider module is expected to expose the following:

*   **`async generate_response(...)` function:**
    *   **Signature:** `(inst, system_prompt, dialogue_history, ...)`
    *   **Functionality:** Takes a standard set of inputs (user instruction, system prompt, history, etc.) and translates them into the specific format required by its target API (e.g., OpenAI's message format, Gemini's content parts). It handles API authentication, makes the request, and handles API-specific errors.
    *   **Returns:** A tuple `(thread, generator)`. For API-based models, `thread` is `None`. `generator` is an async generator that yields the streamed response chunks.
*   **Custom Exception Class:** A custom exception (e.g., `OpenAIError`, `GeminiError`) that inherits from a base `Exception`. This allows the `ResponseGenerator` to catch specific API failures and gracefully fall back to the next model in the priority list.

## Supported Providers

*   **[OpenAI](./openai.md):** Wrapper for the OpenAI API (e.g., GPT-4o).
*   **[Gemini](./gemini.md):** Wrapper for the Google Gemini API.
*   **[Claude](./claude.md):** Wrapper for the Anthropic Claude API.
*   **Local Model:** The logic for the local model is handled directly within [`gpt/core/response_generator.py`](../core/response_generator.md).