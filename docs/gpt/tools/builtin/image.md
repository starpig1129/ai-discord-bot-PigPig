# Built-in Tools - Image Generation

**File:** [`gpt/tools/builtin/image.py`](gpt/tools/builtin/image.py)

This module defines the `generate_image` tool, which exposes the functionality of the `ImageGenerationCog` to the AI.

## `@tool` `async def generate_image(...)`

This function allows the AI to request the generation or editing of an image.

*   **Parameters:**
    *   `context` (ToolExecutionContext): The standard execution context.
    *   `prompt` (str): The descriptive text to guide the image generation process.
    *   `image_url` (Optional[str]): An optional URL to an image that will be used as a starting point for editing.
*   **Logic:**
    1.  It retrieves the `ImageGenerationCog` instance from the bot.
    2.  If an `image_url` is provided, it asynchronously downloads the image and prepares it as an input.
    3.  It calls the `_generate_image_logic` method on the cog, passing the prompt and any input images. This is the same core logic function used by the `/generate_image` slash command.
    4.  The `ImageGenerationCog` handles the actual image generation and sends the resulting image file to the channel.
*   **Returns:** A string confirming the result of the operation (e.g., "Image generated successfully." or an error message). The image file itself is sent by the underlying cog, not returned by the tool.