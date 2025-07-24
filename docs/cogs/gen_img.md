# Image Generation Cog

**File:** [`cogs/gen_img.py`](cogs/gen_img.py)

This cog provides powerful image generation and editing capabilities directly within Discord. It integrates with Google's Gemini API for advanced generation and can also leverage a local InstructPix2Pix model for image editing tasks.

## Features

*   **Multi-modal Interaction:** Users can provide both text prompts and input images for generation or editing.
*   **Dual Model Support:**
    *   **Gemini API:** Used for high-quality image generation from text or image prompts.
    *   **Local Model (InstructPix2Pix):** Used for instruction-based image editing (e.g., "turn the sky blue").
*   **Conversational History:** The cog maintains a short-term memory of the conversation in a channel, allowing for follow-up instructions and iterative image refinement.

## Main Command

### `/generate_image`

The primary command for all image generation and editing tasks.

*   **Parameters:**
    *   `prompt` (str): The text instruction for what to generate or how to edit an image.
*   **Usage:**
    *   **Text-to-Image:** Simply provide a descriptive prompt.
        *   Example: `/generate_image prompt: a photorealistic cat wearing a wizard hat`
    *   **Image Editing:** Send an image in the channel first, then use the command with an editing instruction.
        *   Example: (After sending a picture of a dog) `/generate_image prompt: make the dog wear sunglasses`

## Core Logic

### `_generate_image_logic(...)`

This is the central function that orchestrates the image generation process. It determines which model to use based on the input and availability.

1.  It first attempts to use the **Gemini API**, which is capable of handling both text and image inputs.
2.  If the Gemini API fails or is not suitable, and an input image is provided, it can fall back to the **local InstructPix2Pix model**.
3.  It manages the conversational history for the channel, allowing for context-aware follow-up commands.

### `generate_with_gemini(...)`

Handles the interaction with the Gemini API. It constructs a payload including the prompt, any input images (as base64 strings), and the recent conversation history, then sends it to the API.

### `generate_with_local_model(...)`

Handles image editing using the local `StableDiffusionInstructPix2PixPipeline`. It takes an input image and a text prompt to perform the edit.