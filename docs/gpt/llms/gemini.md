# LLM Providers - Gemini

**File:** [`gpt/llms/gemini.py`](gpt/llms/gemini.py)

This module provides a sophisticated wrapper for interacting with the Google Gemini API. It is the most feature-rich of the LLM providers, supporting multi-modal inputs, structured JSON responses, and caching.

## `async generate_response(...)`

This function implements the standard interface for generating a response from the Gemini API.

*   **Parameters:**
    *   `response_schema` (Optional[Type[BaseModel]]): This is a key feature. If a Pydantic model is provided, the function will instruct the Gemini API to return a JSON object that strictly conforms to that model's schema. This is used for structured data extraction, like in the story system's `GMActionPlan`.
*   **Input Formatting (`_build_conversation_contents`):** It translates the generic dialogue history into the `contents` list format required by the Gemini API. It correctly handles the `user`, `model`, and `function` roles.
*   **Multi-modal Support (`_upload_media_files`):** It provides robust support for various input types:
    *   **Images, Audio, Video:** These are uploaded to the Gemini Files API, and a reference to the uploaded file is included in the prompt.
    *   **PDFs:** PDFs are also uploaded via the Files API, allowing the model to perform analysis on their content.
    *   **Fallback:** For images, if the upload fails, it falls back to sending them as inline base64 data.
*   **Caching (`GeminiCacheManager`):** This module includes a caching system that leverages the Gemini API's native caching capabilities.
    *   `_create_context_hash`: It generates a unique hash based on the content of the static parts of the prompt (system prompt, images, PDFs, etc.).
    *   `get_cache_by_key`: It checks if a cache already exists for this content hash.
    *   `create_and_register_cache`: If no cache exists, it uploads the static content (like PDFs) once and creates a `CachedContent` object on the Gemini backend.
    *   Subsequent calls with the same static content will use the cached version, sending only the dynamic parts (like the user's text prompt), which significantly reduces cost and latency.
*   **Error Handling:** It catches API-specific errors and raises a `GeminiError`, allowing for fallback to other models.