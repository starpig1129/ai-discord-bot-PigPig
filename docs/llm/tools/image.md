# Image Generation Tools

## Overview

The `ImageTools` class provides LangChain-compatible tools for generating images using the `ImageGenerationCog`. It allows the LLM to create visual content based on text descriptions, supporting both text-to-image and image-to-image (img2img) workflows.

## Class: ImageTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

**Parameters:**
- `runtime`: Orchestrator request containing bot, message, and logger.

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: A list containing the `generate_image` tool.

### Tool: generate_image

```python
@tool
async def generate_image(
    prompt: str, image_url: Optional[str] = None
) -> str:
```

**Parameters:**
- `prompt`: Detailed text description of the desired image.
- `image_url`: Optional URL of a base image for img2img generation.

**Returns:**
- `str`: A status message indicating success or an error description.

**Purpose:**
Invokes the bot's image generation engine (e.g., Midjourney, Stable Diffusion, or DALL-E) to create and send an image to the Discord channel.

**Features:**
- **Prompt Expansion**: The LLM is instructed to expand simple prompts into highly detailed, descriptive ones for better artistic results.
- **img2img Support**: If a user provides an image URL, it can be used as a reference or base for the new generation.
- **Progress Notification**: Sends a transient "Generating..." message to provide immediate feedback to the user.
- **Base64/Binary Support**: Handles various attachment formats (base64, raw bytes) for robust delivery.
- **Auto-Cleanup**: Automatically deletes transient notification messages after generation is complete.

## Integration

- **ImageGenerationCog**: The core logic resides in `cogs/gen_img.py`, which handles API requests to image providers.
- **PIL (Pillow)**: Used for image processing and verification.
- **Discord.py**: Used for sending the final `.png` or `.jpg` files as attachments.

## Usage Examples

**Text-to-Image:**
```python
# Simple prompt
result = await generate_image(prompt="A futuristic city with neon lights, cyberpunk style")
```

**Image-to-Image:**
```python
# Modifying an existing image
result = await generate_image(
    prompt="Make this person look like a wizard",
    image_url="https://example.com/photo.jpg"
)
```

## Performance & Constraints

- **Latency**: Image generation can take 10-60 seconds depending on the provider and queue depth.
- **Safety Filtering**: Prompts are subject to provider-level safety filters; failures are reported as errors.
- **Asset Size**: Generated images are usually 1MB-5MB and are sent directly as Discord attachments.

## Dependencies

- `cogs.gen_img.ImageGenerationCog`: Backend generation logic.
- `PIL.Image`: For image handling.
- `aiohttp`: For downloading source images (img2img).
- `base64`: For decoding provider responses.
