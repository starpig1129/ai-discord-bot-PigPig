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
from addons.logging import get_logger
from typing import Optional, TYPE_CHECKING

import aiohttp
import base64
import discord
from PIL import Image
from langchain_core.tools import tool

from function import func

if TYPE_CHECKING:
    from cogs.gen_img import ImageGenerationCog
    from llm.schema import OrchestratorRequest


# Module-level logger
_logger = get_logger(server_id="Bot", source="llm.tools.image")


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

            # Send generated image to Discord channel or return content
            message = getattr(runtime, "message", None)
            channel = getattr(message, "channel", None) if message else None
            try:
                # Legacy: a discord.File was returned directly
                if result.get("file"):
                    discord_file = result["file"]
                    if channel:
                        await channel.send(files=[discord_file])
                        return "Image sent successfully."
                    return "Error: No channel available to send the image."

                # Newer path: attachments may be base64 strings or raw bytes
                attachments = result.get("attachments") or []
                files = []
                for att in attachments:
                    try:
                        if att.get("type") != "image":
                            continue
                        data_bytes = None
                        # Support legacy/new fields: prefer 'data_base64' (string)
                        if "data_base64" in att and att["data_base64"] is not None:
                            data_bytes = base64.b64decode(att["data_base64"])
                        # Support raw binary data in 'data' (bytes/bytearray/memoryview)
                        elif "data" in att and att["data"] is not None:
                            raw = att["data"]
                            if isinstance(raw, (bytes, bytearray, memoryview)):
                                data_bytes = bytes(raw)
                            elif isinstance(raw, str):
                                # The string may be base64 or plain text. Try base64 decode; on failure use utf-8 bytes.
                                try:
                                    data_bytes = base64.b64decode(raw)
                                except Exception:
                                    data_bytes = raw.encode("utf-8")
                            else:
                                raise TypeError(f"Unsupported attachment data type: {type(raw)}")
                        if data_bytes:
                            fname = att.get("filename", "generated_image.png")
                            files.append(discord.File(io.BytesIO(data_bytes), filename=fname))
                    except Exception as e:
                        # Report conversion errors via func.report_error and log context
                        await func.report_error(e, "converting attachment to discord.File")
                        logger.error("Attachment conversion failed", exception=e)

                content = result.get("content")
                if files:
                    if channel:
                        await channel.send(content=content, files=files)
                        return "Image sent successfully."
                    return "Error: No channel available to send the image."

                if content:
                    return content

                return "Image generated successfully, but no image data was returned."
            except Exception as e:
                await func.report_error(e, "sending generated image failed")
                return f"Error: Failed to send generated image: {e}"

        return [generate_image]
