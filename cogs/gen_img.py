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
import discord
from discord import app_commands
from discord.ext import commands
import io
import asyncio
import base64
import aiohttp
from google import genai
from google.genai import types
from PIL import Image
from typing import List, Optional, Dict
from addons.tokens import tokens
from llm.utils.media import image_to_base64
from .language_manager import LanguageManager
from llm.utils.send_message import safe_edit_message
from function import func
from addons.logging import get_logger

# Module-level logger. Use "Bot" as default server_id for module-level events.
log = get_logger(server_id="Bot", source=__name__)


class ImageGenerationCog(commands.Cog, name="ImageGenerationCog"):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None
        self.session = aiohttp.ClientSession()
        self.tokens = tokens
        self.client = genai.Client(api_key=self.tokens.google_api_key)
        self.model_id = "timbrooks/instruct-pix2pix"
        self.conversation_history: Dict[int, List[Dict]] = {}
        self.logger = get_logger(server_id="Bot", source="gen_img")

    async def cog_load(self):
        """Initialize the language manager when the cog is loaded"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    def _get_conversation_history(self, channel_id: int) -> List[Dict]:
        """Get the conversation history for a specific channel"""
        return self.conversation_history.get(channel_id, [])

    def _update_conversation_history(self, channel_id: int, role: str, content: str, images: Optional[List[Image.Image]] = None):
        """Update the conversation history"""
        if channel_id not in self.conversation_history:
            self.conversation_history[channel_id] = []
        
        entry = {"role": role, "content": content}
        if images:
            entry["images"] = images
            
        self.conversation_history[channel_id].append(entry)
        if len(self.conversation_history[channel_id]) > 10:
            self.conversation_history[channel_id].pop(0)

    async def _generate_image_logic(
        self,
        prompt: str,
        guild_id: str,
        channel_id: int,
        input_images: Optional[List[Image.Image]] = None,
        channel: Optional[discord.TextChannel] = None
    ) -> Dict:
        """
        Core image generation logic.
        
        Returns a dict containing 'content' and/or 'file', or a dict with 'error'.
        """
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        input_images = input_images or []

        try:
            history = self._get_conversation_history(channel_id)
            
            try:
                image_buffer, response_text = await self.generate_with_gemini(prompt, input_images, history)
                
                self._update_conversation_history(channel_id, "user", prompt, input_images)
                
                response_text = response_text or ""
                
                if image_buffer:
                    # Do not return discord.File; return base64-encoded attachment description so upstream can send uniformly
                    image_buffer.seek(0)
                    try:
                        raw = image_buffer.read()
                        if not raw:
                            self.logger.warning("image_buffer is empty (Gemini branch); treating as failure")
                            raise ValueError("empty_image_buffer")
                        b64 = base64.b64encode(raw).decode("utf-8")
                    except Exception as enc_err:
                        asyncio.create_task(func.report_error(enc_err, "Gemini image encoding failed"))
                        self.logger.error(f"Gemini image encoding failed: {enc_err}")
                        raise

                    success_message = self.lang_manager.translate(
                        guild_id, "commands", "generate_image", "responses", "image_generated"
                    )
                    self._update_conversation_history(
                        channel_id, "assistant", (response_text or success_message).strip(), [image_buffer]
                    )
                    payload = {
                        "content": (response_text or "").strip() or success_message,
                        "attachments": [
                            {
                                "type": "image",
                                "filename": "generated_image.png",
                                "mime_type": "image/png",
                                "data_base64": b64,
                                "caption": None
                            }
                        ]
                    }
                    self.logger.info("Generation succeeded (Gemini branch); returning with attachment")
                    return payload
                elif response_text.strip():

                    error_message = self.lang_manager.translate(
                        guild_id, "commands", "generate_image", "responses", "all_methods_failed"
                    )
                    return {"error": error_message}
            except Exception as e:
                await func.report_error(e, "Gemini generation process failed")
                error_message = self.lang_manager.translate(
                    guild_id, "commands", "generate_image", "errors", "gemini_generation_error", error=str(e)
                )
                self.logger.error(error_message)

            if channel:
                image_buffer = await self.generate_with_local_model(channel, prompt, guild_id=guild_id)
                if image_buffer:
                    image_buffer.seek(0)
                    try:
                        raw = image_buffer.read()
                        if not raw:
                            self.logger.warning("image_buffer is empty (Local branch); treating as failure")
                            raise ValueError("empty_image_buffer")
                        b64 = base64.b64encode(raw).decode("utf-8")
                    except Exception as enc_err:
                        asyncio.create_task(func.report_error(enc_err, "Local model image encoding failed"))
                        self.logger.error(f"Local model image encoding failed: {enc_err}")
                        raise
                    self.logger.info("Generation succeeded (Local branch); returning with attachment")
                    return {
                        "attachments": [
                            {
                                "type": "image",
                                "filename": "generated_image.png",
                                "mime_type": "image/png",
                                "data_base64": b64,
                                "caption": None
                            }
                        ]
                    }
                else:
                    self.logger.warning("Local branch did not produce an image; returning error")

            error_message = self.lang_manager.translate(
                guild_id, "commands", "generate_image", "responses", "all_methods_failed"
            )
            return {"error": error_message}

        except Exception as e:
            await func.report_error(e, f"generate_image_logic: {e}")
            error_message = self.lang_manager.translate(
                guild_id, "commands", "generate_image", "responses", "general_error", error=str(e)
            )
            self.logger.error(f"Image generation process error: {str(e)}")
            return {"error": error_message}

    @app_commands.command(name="generate_image", description="生成或編輯圖片")
    @app_commands.describe(prompt="用於生成或編輯圖片的提示文字")
    async def generate_image_command(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        
        guild_id = str(interaction.guild_id)
        channel_id = interaction.channel_id
        
        input_images = []
        if interaction.channel.last_message and interaction.channel.last_message.attachments:
            for attachment in interaction.channel.last_message.attachments:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    try:
                        async with self.session.get(attachment.url) as response:
                            image_data = await response.read()
                        img = Image.open(io.BytesIO(image_data))
                        input_images.append(img)
                    except Exception as e:
                        await func.report_error(e, f"generate_image_command attachment read: {e}")
                        self.logger.error(f"Failed to read attachment image: {e}")

        result = await self._generate_image_logic(
            prompt=prompt,
            guild_id=guild_id,
            channel_id=channel_id,
            input_images=input_images,
            channel=interaction.channel
        )

        # Slash command still uses immediate reply but supports attachments (base64 → discord.File)
        if "error" in result:
            await interaction.followup.send(result["error"])
        else:
            files = []
            attachments = result.get("attachments") or []
            for att in attachments:
                try:
                    if att.get("type") == "image" and "data_base64" in att:
                        data = base64.b64decode(att["data_base64"])
                        fname = att.get("filename", "image.png")
                        files.append(discord.File(io.BytesIO(data), filename=fname))
                except Exception as e:
                    await func.report_error(e, "Slash command file conversion failed")
                    self.logger.error(f"Slash reply conversion failed: {e}")
            content = result.get("content")
            if files:
                await interaction.followup.send(content=content, files=files)
            else:
                await interaction.followup.send(content=content)

    def _image_to_base64(self, image: Image.Image) -> str:
        """Convert a PIL Image to a base64-encoded string"""
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str

    async def generate_with_gemini(self, prompt: str, image_input: List[Image.Image], dialogue_history: List[Dict]) -> tuple[Optional[io.BytesIO], Optional[str]]:
        """Generate images using the Gemini API"""
        try:
            content_parts = []
            if dialogue_history:
                history_content = "\n".join([f"{msg['role']}: {msg['content']}" for msg in dialogue_history])
                full_prompt = f"{history_content}\nUser: {prompt}"
                content_parts.append({"text": full_prompt})
            else:
                content_parts.append({"text": prompt})

            if image_input and isinstance(image_input, list):
                for img in image_input:
                    content_parts.append({
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": image_to_base64(img)
                        }
                    })
            response = await asyncio.to_thread(
                lambda: self.client.models.generate_content(
                    model="gemini-2.0-flash-preview-image-generation",
                    contents=content_parts,
                    config=types.GenerateContentConfig(
                    response_modalities=['Text', 'Image']
                    )
                )
            )
            image_buffer = None
            response_text = []
            
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text is not None:
                    response_text.append(part.text)
                elif hasattr(part, 'inline_data') and part.inline_data:
                    try:
                        if isinstance(part.inline_data.data, bytes):
                            image_bytes = part.inline_data.data
                        else:
                            # 相容舊版本 SDK（返回 base64 字符串）
                            image_bytes = base64.b64decode(part.inline_data.data)
                        
                        image_buffer = io.BytesIO()
                        image = Image.open(io.BytesIO(image_bytes))
                        image.save(image_buffer, format="PNG")
                        image_buffer.seek(0)
                    except Exception as e:
                        await func.report_error(e, "Gemini image processing failed")
                        if self.lang_manager:
                            error_msg = self.lang_manager.translate(
                                "0",
                                "commands",
                                "generate_image",
                                "errors",
                                "image_processing_error",
                                error=str(e)
                            )
                            self.logger.error(error_msg)
                        else:
                            self.logger.error(f"Image processing error: {str(e)}")
            
            final_text = " ".join(text for text in response_text if text)
            return image_buffer, final_text or None
            
        except Exception as e:
            await func.report_error(e, f"generate_with_gemini: {e}")
            if self.lang_manager:
                error_msg = self.lang_manager.translate(
                    "0",
                    "commands",
                    "generate_image",
                    "errors",
                    "gemini_generation_error",
                    error=str(e)
                )
                self.logger.error(error_msg)
            else:
                self.logger.error(f"Gemini API generation error: {str(e)}")
            return None, None

    async def generate_with_local_model(self, channel, prompt: str, n_steps: int = 10, message_to_edit: discord.Message = None, guild_id: str = None):
        """Generate images using a local model"""
        try:
            if not hasattr(self, 'pipe') or self.pipe is None:
                return None
                
            if message_to_edit:
                processing_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "generate_image",
                    "responses",
                    "local_model_processing"
                )
                await safe_edit_message(message_to_edit, processing_message, caller_name="ImageGenerationCog")
            else:
                processing_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "generate_image",
                    "responses",
                    "local_model_processing"
                )
                message = await channel.send(processing_message)

            if channel.last_message and channel.last_message.attachments:
                for attachment in channel.last_message.attachments:
                    if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                        async with self.session.get(attachment.url) as response:
                            image_data = await response.read()
                        image = Image.open(io.BytesIO(image_data)).convert('RGB')
                        break
                else:
                    image = Image.new("RGB", (512, 512), color="white")
            else:
                image = Image.new("RGB", (512, 512), color="white")

            images = await asyncio.to_thread(
                self.pipe,
                prompt,
                image=image,
                num_inference_steps=n_steps,
                image_guidance_scale=1
            )
            
            image_buffer = io.BytesIO()
            images[0].save(image_buffer, format="PNG")
            image_buffer.seek(0)

            if message_to_edit:
                success_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "generate_image",
                    "responses",
                    "local_model_complete"
                )
                await safe_edit_message(message_to_edit, success_message, caller_name="ImageGenerationCog")
            return image_buffer

        except Exception as e:
            await func.report_error(e, f"generate_with_local_model: {e}")
            if self.lang_manager:
                error_msg = self.lang_manager.translate(
                    guild_id or "0",
                    "commands",
                    "generate_image",
                    "errors",
                    "local_model_error",
                    error=str(e)
                )
                self.logger.error(error_msg)
            else:
                self.logger.error(f"Local model generation error: {str(e)}")
                return None

    async def cog_unload(self):
        """清理資源"""
        if hasattr(self, 'session'):
            await self.session.close()

async def setup(bot):
    await bot.add_cog(ImageGenerationCog(bot))
