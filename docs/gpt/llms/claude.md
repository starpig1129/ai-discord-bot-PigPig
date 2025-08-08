# LLM Providers - Claude

**File:** [`gpt/llms/claude.py`](gpt/llms/claude.py)

This module provides a wrapper for interacting with the Anthropic Claude API, specifically the Claude 3.5 Sonnet model.

## `async generate_response(...)`

This function implements the standard interface for generating a response from the Claude API.

*   **Input Formatting:** It formats the conversation history into the single, continuous string format required by the Claude Completions API, using `HUMAN_PROMPT` and `AI_PROMPT` to delineate turns.
*   **Multi-modal Support:** It supports image and video inputs.
    *   **Images:** Image data is expected to be passed in a specific format (details depend on the calling function).
    *   **Video:** It uses a helper function `extract_video_frames` to extract a set number of frames from a video file. These frames are then converted to base64 strings and embedded in the prompt.
*   **Streaming:** It makes a streaming request to the API and yields the response chunks as they are received.
*   **Error Handling:** It catches common API errors (like invalid API key, rate limits, quota exceeded) and raises a specific `ClaudeError` with a user-friendly message, allowing the `ResponseGenerator` to gracefully fall back to another model.