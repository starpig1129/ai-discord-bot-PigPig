# GPT Core - Response Generator

**File:** [`gpt/core/response_generator.py`](gpt/core/response_generator.py)

This module is the lowest-level component in the AI pipeline, responsible for direct communication with various Large Language Models (LLMs). It acts as an abstraction layer, providing a single, unified function to generate responses while handling the complexities of different APIs and model types.

## `generate_response(...)`

This is the primary function of the module. It takes a prompt and context, and returns a response from the best available LLM.

*   **Parameters:**
    *   `inst` (str): The user's instruction or prompt.
    *   `system_prompt` (str): The system prompt defining the AI's personality and task.
    *   `dialogue_history` (Optional[list]): The history of the conversation.
    *   `image_input`, `audio_input`, `video_input`: Optional multi-modal inputs.
    *   `response_schema` (Optional[Type[BaseModel]]): An optional Pydantic model. If provided (and the model supports it, like Gemini), the LLM is instructed to return a JSON object that conforms to this schema.
*   **Returns:** A tuple `(thread, generator)`.
    *   `thread`: The `threading.Thread` object if a local model is used (for managing the background process).
    *   `generator`: An asynchronous generator that yields the response chunks as they are streamed from the model. If a `response_schema` is used, this will be the parsed Pydantic object instead of a generator.

### Model Priority and Fallback

The function's key feature is its robust fallback mechanism. It iterates through a list of models defined in `settings.model_priority` (e.g., `["gemini", "local", "openai", "claude"]`).

1.  It first checks if the highest-priority model is available (e.g., if the API key is set).
2.  If available, it attempts to generate a response using that model's specific generation function (e.g., `gemini_generate`).
3.  If the API call fails for any reason (e.g., network error, content safety filter), it logs the error and automatically moves to the next model in the priority list.
4.  This process continues until a response is successfully generated or all available models have been tried.

## Local Model Management

The module also contains the global state and management functions for the locally hosted model.

*   **`global_model`, `global_tokenizer`:** Global variables that hold the loaded model and tokenizer instances.
*   **`get_model_and_tokenizer()`:** A thread-safe asynchronous function that lazy-loads the local model the first time it's needed.
*   **`set_model_and_tokenizer(...)`:** A function (typically called by the `ModelManagement` cog) to load a model into the global variables.
*   **`local_generate(...)`:** The specific generation function for the local model, handling the tokenization, streaming, and multi-modal input processing.