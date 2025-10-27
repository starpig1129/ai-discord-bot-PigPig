# MIT License
#
# Copyright (c) 2024 starpig1129
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import io
import aiohttp
from typing import Optional, TYPE_CHECKING
import discord

from PIL import Image

from gpt.tools.registry import tool
from gpt.tools.tool_context import ToolExecutionContext
from gpt.core.message_sender import gpt_message
import function as func

if TYPE_CHECKING:
    from cogs.gen_img import ImageGenerationCog


@tool
async def generate_image(
    context: ToolExecutionContext, prompt: str, image_url: Optional[str] = None
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

    cog: Optional["ImageGenerationCog"] = context.bot.get_cog("ImageGenerationCog")
    if not cog:
        logger.error("ImageGenerationCog not found.")
        return "Error: Image generation cog is not available."

    input_images = []
    if image_url:
       try:
           async with cog.session.get(image_url) as response:
               response.raise_for_status()
               image_data = await response.read()
               img = Image.open(io.BytesIO(image_data))
               input_images.append(img)
       except aiohttp.ClientResponseError as e:
           if e.status == 404:
               logger.warning(f"Failed to download image from {image_url} (404 Not Found).")
               return "Error: The provided image URL is invalid or has expired (404 Not Found)."
           else:
               logger.error(
                   f"Failed to download image from URL '{image_url}': {e}"
               )
               return f"Error: Failed to download the provided image URL. Status: {e.status}"
       except Exception as e:
           await func.func.report_error(e, f"processing image from URL '{image_url}'")
           return f"Error: Failed to process the provided image URL. {e}"

    guild_id = getattr(context, "guild_id", "0")
    channel_id = getattr(context, "channel_id", 0)

    result = await cog._generate_image_logic(
        prompt=prompt,
        guild_id=guild_id,
        channel_id=channel_id,
        input_images=input_images,
        channel=context.message.channel,
    )

    if "error" in result:
        logger.error(f"Image generation failed: {result['error']}")
        return f"Error: {result['error']}"

    if "file" in result and result["file"]:
        discord_file = result["file"]
        
        # 從 context 中獲取 message 和 message_to_edit
        message = context.message
        message_to_edit = context.message_to_edit
        
        await gpt_message(
            message_to_edit=message_to_edit,
            message=message,
            prompt='',
            history_dict={},
            files=[discord_file]
        )
        return "Image sent successfully."

    if "content" in result and result["content"]:
        return result["content"]

    return "Image generated successfully, but no image data was returned."