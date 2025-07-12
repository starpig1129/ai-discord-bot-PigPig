# MIT License
# Copyright (c) 2024 starpig1129

import io
import base64
import aiohttp
import asyncio
from PIL import Image
from typing import Optional

from gpt.tools.registry import tool
from gpt.tools.tool_context import ToolExecutionContext
from addons.settings import TOKENS

# Lazy initialization for the Gemini client
gemini_client = None

def get_gemini_client():
    """Initializes and returns the Gemini client."""
    global gemini_client
    if gemini_client is None:
        from google import genai
        tokens = TOKENS()
        if not tokens.gemini_api_key:
            raise ValueError("Gemini API key is not configured in TOKENS.")
        gemini_client = genai.Client(api_key=tokens.gemini_api_key)
    return gemini_client

def image_to_base64(image: Image.Image) -> str:
    """Converts a PIL Image to a base64 encoded string."""
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

@tool
async def generate_image(
    context: ToolExecutionContext,
    prompt: str,
    image_url: Optional[str] = None
) -> str:
    """Generates an image based on a text prompt and an optional base image.

    This tool leverages the core image generation logic to create or modify images.
    It can be used to visualize ideas, create art, or generate content.

    Args:
        context (ToolExecutionContext): The execution context, providing access to the bot, logger, etc.
        prompt (str): The descriptive text to guide the image generation process.
        image_url (Optional[str]): An optional URL to an image that will be used as a starting point.

    Returns:
        str: A success message with the image details or an error message.
    """
    logger = context.logger
    logger.info(f"Tool 'generate_image' called with prompt: '{prompt}'")

    cog = context.bot.get_cog("ImageGenerationCog")
    if not cog:
        logger.error("ImageGenerationCog not found.")
        return "Error: Image generation cog is not available."

    input_images = []
    if image_url:
        try:
            # Use the cog's session to be consistent
            async with cog.session.get(image_url) as response:
                response.raise_for_status()
                image_data = await response.read()
                img = Image.open(io.BytesIO(image_data))
                input_images.append(img)
        except Exception as e:
            logger.error(f"Failed to download or process image from URL '{image_url}': {e}")
            return f"Error: Failed to process the provided image URL. {e}"

    # We need a guild_id and channel_id for the logic, but they might not be in the tool context.
    # We'll use defaults. History features will be limited.
    # Assuming context might have some discord-related info in the future.
    guild_id = getattr(context, "guild_id", "0")
    channel_id = getattr(context, "channel_id", 0)

    result = await cog._generate_image_logic(
        prompt=prompt,
        guild_id=guild_id,
        channel_id=channel_id,
        input_images=input_images,
        channel=None # No direct access to a discord.TextChannel object here
    )

    if "error" in result:
        logger.error(f"Image generation failed: {result['error']}")
        return f"Error: {result['error']}"
    
    # The tool now returns a text confirmation. The image is sent by the logic itself
    # via the response mechanism, which is more aligned with how the bot works.
    # We can return the text part of the response if it exists.
    if "content" in result and result["content"]:
        return result["content"]
    
    return "Image generated successfully."