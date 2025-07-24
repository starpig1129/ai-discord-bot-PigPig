# GPT System - Utilities

**Files:**
*   [`gpt/utils/media.py`](gpt/utils/media.py)
*   [`gpt/utils/file_watcher.py`](gpt/utils/file_watcher.py)
*   [`gpt/cache_utils.py`](gpt/cache_utils.py)

This document covers various utility modules that provide helper functions for media processing, file monitoring, and cache management.

## Media Processing

**File:** [`gpt/utils/media.py`](gpt/utils/media.py)

This module contains functions for handling multi-modal inputs.

*   **`process_attachment_data(message)`:** This is the main function. It iterates through the attachments of a Discord message, identifies their file type, and processes them accordingly.
    *   **Images:** Converts various image formats into a standardized PIL Image object.
    *   **PDFs:** Uses the `pdf2image` library to convert each page of a PDF into a PIL Image object.
    *   **Videos:** Uses the `decord` library to extract a set number of frames (`MAX_NUM_FRAMES`) uniformly from the video, converting each frame into a PIL Image object.
*   **`image_to_base64(pil_image)`:** A helper function to convert a PIL Image object into a base64 string, which is required for some LLM APIs.

## File Watcher

**File:** [`gpt/utils/file_watcher.py`](gpt/utils/file_watcher.py)

The `FileWatcher` class provides a simple, cross-platform way to monitor files for changes.

*   **`watch_file(path, callback)`:** Starts monitoring a file at a given `path`. When the file's modification time changes, the `callback` function is executed.
*   **Implementation:** It runs a loop in a separate `threading.Thread` to periodically check the modification times of all watched files, ensuring it doesn't block the bot's main asynchronous event loop.
*   **Usage:** This is used by the legacy `PromptManager` to automatically reload the `systemPrompt.yaml` file when it is edited.

## Gemini Cache Utilities

**File:** [`gpt/cache_utils.py`](gpt/cache_utils.py)

The `CacheHelper` class provides a simplified, high-level interface for interacting with the Gemini API's native caching capabilities.

*   **`create_system_cache(system_prompt, ...)`:** A convenience function to create a Gemini cache based only on a system prompt. It checks if a cache with the same prompt already exists to avoid duplicates.
*   **`create_conversation_cache(system_prompt, conversation_history, ...)`:** Creates a cache that includes both a system prompt and a specific conversation history.
*   **`cleanup_old_caches()`:** A function to clear old or expired caches.