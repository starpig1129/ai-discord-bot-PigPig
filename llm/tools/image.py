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
import logging
from typing import Optional, TYPE_CHECKING
 
from PIL import Image
 
from langchain_core.tools import tool
from function import func

if TYPE_CHECKING:
    from cogs.gen_img import ImageGenerationCog
    from main import bot
    from llm.schema import OrchestratorRequest


class ImageTools:
    def __init__(self, runtime: "OrchestratorRequest"):
        self.runtime = runtime

    @tool
    async def generate_image(
        self, prompt: str, image_url: Optional[str] = None
    ) -> str:
        """Image generator wrapper for LLM tools.

        - Delegates execution to a cog and reports exceptions via func.report_error.

        Args:
            prompt: Text prompt.
            image_url: Optional base image URL; if provided, will be downloaded and used as the input image.
        Returns:
            Success or error message (string).
        """
        # runtime is an OrchestratorRequest: use its explicit attributes.
        logger = getattr(self.runtime, "logger", logging.getLogger(__name__))
        logger.info("Tool 'generate_image' called", extra={"prompt": prompt})
        bot = getattr(self.runtime, "bot", None)
        if not bot:
            logger.error("Bot instance not available in runtime.")
            return "Error: Bot instance not available."
        cog: Optional["ImageGenerationCog"] = bot.get_cog("ImageGenerationCog")
        if not cog:
            logger.error("ImageGenerationCog not found.")
            return "Error: Image generation cog is not available."

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
                        "Failed to download image (404).", extra={"url": image_url}
                    )
                    return "Error: The provided image URL is invalid or has expired (404 Not Found)."
                await func.report_error(e, f"downloading image from '{image_url}'")
                return f"Error: Failed to download image. Status: {getattr(e, 'status', 'unknown')}"
            except Exception as e:  # pragma: no cover - external IO
                await func.report_error(
                    e, f"processing image from URL '{image_url}'"
                )
                return f"Error: Failed to process the provided image URL. {e}"

        message_obj = getattr(self.runtime, "message", None)
        guild_id = (
            str(message_obj.guild.id)
            if message_obj and getattr(message_obj, "guild", None)
            else "0"
        )
        channel_id = getattr(getattr(message_obj, "channel", None), "id", 0)
 
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

        if not isinstance(result, dict):
            logger.warning(
                "Image generation returned unexpected type.",
                extra={"type": type(result)},
            )
            return str(result)

        if "error" in result and result["error"]:
            logger.error(
                "Image generation cog returned error.", extra={"error": result["error"]}
            )
            return f"Error: {result['error']}"

        if result.get("file"):
            discord_file = result["file"]
            # Obtain message/channel from runtime
            message = getattr(self.runtime, "message", None)
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