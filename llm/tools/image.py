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

"""Image generation tools for LLM integration.

This module provides LangChain-compatible tools for generating images
using the ImageGenerationCog.
"""

import io
import logging
from typing import Optional, TYPE_CHECKING

import aiohttp
from PIL import Image
from langchain_core.tools import tool

from function import func

if TYPE_CHECKING:
    from cogs.gen_img import ImageGenerationCog
    from llm.schema import OrchestratorRequest


# Module-level logger
_logger = logging.getLogger(__name__)


class ImageTools:
    """Container class for image generation tools.
    
    This class holds the runtime context and provides factory methods
    to create tool instances bound to that context.
    
    Attributes:
        runtime: The orchestrator request containing bot, message, and logger.
    """

    def __init__(self, runtime: "OrchestratorRequest"):
        """Initializes ImageTools with runtime context.
        
        Args:
            runtime: The orchestrator request object containing necessary context.
        """
        self.runtime = runtime

    def get_tools(self) -> list:
        """Returns a list of LangChain tools bound to this runtime.
        
        Returns:
            A list containing the generate_image tool with runtime context.
        """
        runtime = self.runtime
        
        @tool
        async def generate_image(
            prompt: str, image_url: Optional[str] = None
        ) -> str:
            """Generates an image based on a text prompt.

            This tool creates images using AI generation. Optionally accepts
            a base image URL for image-to-image generation.

            Args:
                prompt: Text description of the desired image.
                image_url: Optional URL of a base image for img2img generation.
                    If provided, the image will be downloaded and used as input.

            Returns:
                A success message if the image was generated and sent,
                or an error message describing what went wrong.
            """
            logger = getattr(runtime, "logger", _logger)
            logger.info(
                "Tool 'generate_image' called",
                extra={"prompt": prompt, "image_url": image_url}
            )

            # Retrieve bot instance from runtime
            bot = getattr(runtime, "bot", None)
            if not bot:
                logger.error("Bot instance not available in runtime.")
                return "Error: Bot instance not available."

            # Retrieve ImageGenerationCog
            cog: Optional["ImageGenerationCog"] = bot.get_cog("ImageGenerationCog")
            if not cog:
                logger.error("ImageGenerationCog not found.")
                return "Error: Image generation cog is not available."

            # Download input image if URL is provided
            input_images = []
            if image_url:
                try:
                    async with cog.session.get(image_url) as response:
                        response.raise_for_status()
                        data = await response.read()
                        img = Image.open(io.BytesIO(data)).convert("RGBA")
                        input_images.append(img)
                except aiohttp.ClientResponseError as e:
                    if getattr(e, "status", None) == 404:
                        logger.warning(
                            "Failed to download image (404).",
                            extra={"url": image_url}
                        )
                        return (
                            "Error: The provided image URL is invalid or has "
                            "expired (404 Not Found)."
                        )
                    await func.report_error(
                        e, f"downloading image from '{image_url}'"
                    )
                    return (
                        f"Error: Failed to download image. "
                        f"Status: {getattr(e, 'status', 'unknown')}"
                    )
                except Exception as e:  # pragma: no cover - external IO
                    await func.report_error(
                        e, f"processing image from URL '{image_url}'"
                    )
                    return f"Error: Failed to process the provided image URL. {e}"

            # Extract guild and channel information
            message_obj = getattr(runtime, "message", None)
            guild_id = (
                str(message_obj.guild.id)
                if message_obj and getattr(message_obj, "guild", None)
                else "0"
            )
            channel_id = getattr(getattr(message_obj, "channel", None), "id", 0)

            # Call image generation logic
            try:
                result = await cog._generate_image_logic(
                    prompt=prompt,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    input_images=input_images,
                    channel=getattr(message_obj, "channel", None),
                )
            except Exception as e:
                await func.report_error(
                    e, "calling ImageGenerationCog._generate_image_logic failed"
                )
                return f"Error: Image generation failed: {e}"

            # Process result
            if not isinstance(result, dict):
                logger.warning(
                    "Image generation returned unexpected type.",
                    extra={"type": type(result)},
                )
                return str(result)

            if "error" in result and result["error"]:
                logger.error(
                    "Image generation cog returned error.",
                    extra={"error": result["error"]}
                )
                return f"Error: {result['error']}"

            # Send generated image to Discord channel
            if result.get("file"):
                discord_file = result["file"]
                message = getattr(runtime, "message", None)
                channel = getattr(message, "channel", None) if message else None
                try:
                    if channel:
                        await channel.send(files=[discord_file])
                        return "Image sent successfully."
                    return "Error: No channel available to send the image."
                except Exception as e:
                    await func.report_error(e, "sending generated image failed")
                    return f"Error: Failed to send generated image: {e}"

            if result.get("content"):
                return result["content"]

            return "Image generated successfully, but no image data was returned."

        return [generate_image]
