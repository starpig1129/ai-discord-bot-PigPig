# MIT License

# Copyright (c) 2024 starpig1129

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

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
import torch
from diffusers import StableDiffusionInstructPix2PixPipeline, EulerAncestralDiscreteScheduler
from typing import List, Optional, Dict
from addons.settings import TOKENS
from gpt.vision_tool import image_to_base64

from typing import Optional
from .language_manager import LanguageManager

class ImageGenerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 初始化語言管理器
        self.lang_manager: Optional[LanguageManager] = None
        # 初始化 session
        self.session = aiohttp.ClientSession()
        # 初始化 Gemini API
        tokens = TOKENS()
        self.client = genai.Client(api_key=tokens.gemini_api_key)
        
        # 初始化本地模型
        self.model_id = "timbrooks/instruct-pix2pix"
        #self.pipe = StableDiffusionInstructPix2PixPipeline.from_pretrained(self.model_id, torch_dtype=torch.float16, safety_checker=None)
        #self.pipe.to("cuda:1")
        #self.pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(self.pipe.scheduler.config)
        
        # 存儲對話歷史
        self.conversation_history: Dict[int, List[Dict]] = {}

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    def _get_conversation_history(self, channel_id: int) -> List[Dict]:
        """獲取特定頻道的對話歷史"""
        return self.conversation_history.get(channel_id, [])

    def _update_conversation_history(self, channel_id: int, role: str, content: str, images: Optional[List[Image.Image]] = None):
        """更新對話歷史"""
        if channel_id not in self.conversation_history:
            self.conversation_history[channel_id] = []
        
        entry = {"role": role, "content": content}
        if images:
            entry["images"] = images
            
        self.conversation_history[channel_id].append(entry)
        # 保留最近的10條消息
        if len(self.conversation_history[channel_id]) > 10:
            self.conversation_history[channel_id].pop(0)

    @app_commands.command(name="generate_image", description="生成或編輯圖片")
    @app_commands.describe(prompt="用於生成或編輯圖片的提示文字")
    async def generate_image_command(self, interaction: discord.Interaction, prompt: str):
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        guild_id = str(interaction.guild_id)
        await interaction.response.defer(thinking=True)
        
        try:
            # 獲取輸入圖片（如果有的話）
            input_images = []
            if interaction.channel.last_message and interaction.channel.last_message.attachments:
                for attachment in interaction.channel.last_message.attachments:
                    if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                        async with self.session.get(attachment.url) as response:
                            image_data = await response.read()
                        img = Image.open(io.BytesIO(image_data))
                        input_images.append(img)

            # 獲取對話歷史
            history = self._get_conversation_history(interaction.channel_id)
            
            # 嘗試使用 Gemini API
            try:
                image_buffer, response_text = await self.generate_with_gemini(prompt, input_images, history)
                
                # 更新使用者的輸入到歷史記錄
                self._update_conversation_history(interaction.channel_id, "user", prompt, input_images)
                
                # 準備回應內容
                content = []
                response_text = response_text or ""  # 確保 response_text 不是 None
                if response_text.strip():
                    content.append(response_text)
                
                if image_buffer:
                    # 如果有圖片，添加到歷史記錄並發送
                    file = discord.File(image_buffer, filename="generated_image.png")
                    success_message = self.lang_manager.translate(
                        guild_id,
                        "commands",
                        "generate_image",
                        "responses",
                        "image_generated"
                    )
                    self._update_conversation_history(
                        interaction.channel_id,
                        "assistant",
                        response_text.strip() or success_message,
                        [image_buffer]
                    )
                    await interaction.followup.send(content="\n".join(content), file=file)
                    return
                elif response_text.strip():
                    # 如果只有文字回應
                    self._update_conversation_history(
                        interaction.channel_id,
                        "assistant",
                        response_text,
                        None
                    )
                    await interaction.followup.send(content="\n".join(content))
                    return
            except Exception as e:
                error_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "generate_image",
                    "responses",
                    "gemini_error",
                    error=str(e)
                )
                print(error_message)
                
            # 如果 Gemini 失敗，嘗試使用本地模型
            image = await self.generate_with_local_model(interaction.channel, prompt, guild_id=guild_id)
            if image:
                file = discord.File(image, filename="generated_image.png")
                await interaction.followup.send(content="", file=file)
            else:
                error_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "generate_image",
                    "responses",
                    "all_methods_failed"
                )
                await interaction.followup.send(error_message)
                
        except Exception as e:
            error_message = self.lang_manager.translate(
                guild_id,
                "commands",
                "generate_image",
                "responses",
                "general_error",
                error=str(e)
            )
            print(f"圖片生成過程出現錯誤：{str(e)}")
            await interaction.followup.send(error_message)

    def _image_to_base64(self, image: Image.Image) -> str:
        """將 PIL Image 轉換為 base64 字符串"""
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str

    async def generate_with_gemini(self, prompt: str, image_input: List[Image.Image], dialogue_history: List[Dict]) -> tuple[Optional[io.BytesIO], Optional[str]]:
        """使用 Gemini API 生成圖片"""
        try:
            # 準備內容
            content_parts = []
            # 添加歷史內容和當前提示
            if dialogue_history:
                history_content = "\n".join([f"{msg['role']}: {msg['content']}" for msg in dialogue_history])
                full_prompt = f"{history_content}\nUser: {prompt}"
                content_parts.append({"text": full_prompt})
            else:
                content_parts.append({"text": prompt})

            # 添加圖片
            if image_input and isinstance(image_input, list):
                for img in image_input:
                    content_parts.append({
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": image_to_base64(img)
                        }
                    })
            # 生成回應
            response = await asyncio.to_thread(
                lambda: self.client.models.generate_content(
                    model="gemini-2.0-flash-exp-image-generation",
                    contents=content_parts,
                    config=types.GenerateContentConfig(
                    response_modalities=['Text', 'Image']
                    )
                )
            )
            # 處理回應中的圖片和文字
            image_buffer = None
            response_text = []
            
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text is not None:
                    response_text.append(part.text)
                elif hasattr(part, 'inline_data') and part.inline_data:
                    try:
                        # 創建一個新的緩衝區並將圖片數據寫入
                        image_buffer = io.BytesIO()
                        image_bytes = base64.b64decode(part.inline_data.data)
                        image = Image.open(io.BytesIO(image_bytes))
                        image.save(image_buffer, format="PNG")
                        image_buffer.seek(0)
                    except Exception as e:
                        print(f"圖片處理錯誤：{str(e)}")
                        print(f"Data type: {type(part.inline_data.data)}")
                        print(f"Data preview: {str(part.inline_data.data)[:100]}")
            
            final_text = " ".join(text for text in response_text if text)
            return image_buffer, final_text or None
            
        except Exception as e:
            print(f"Gemini API 生成錯誤：{str(e)}")
            return None, None

    async def generate_with_local_model(self, channel, prompt: str, n_steps: int = 10, message_to_edit: discord.Message = None, guild_id: str = None):
        """使用本地模型生成圖片"""
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
                await message_to_edit.edit(content=processing_message)
            else:
                processing_message = self.lang_manager.translate(
                    guild_id,
                    "commands",
                    "generate_image",
                    "responses",
                    "local_model_processing"
                )
                message = await channel.send(processing_message)

            # 檢查是否有附加圖片
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

            # 使用本地模型生成圖片
            images = await asyncio.to_thread(
                self.pipe,
                prompt,
                image=image,
                num_inference_steps=n_steps,
                image_guidance_scale=1
            )
            
            # 保存圖片
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
                await message_to_edit.edit(content=success_message)
            return image_buffer

        except Exception as e:
            print(f"本地模型生成錯誤：{str(e)}")
            return None

    async def cog_unload(self):
        """清理资源"""
        if hasattr(self, 'session'):
            await self.session.close()

async def setup(bot):
    await bot.add_cog(ImageGenerationCog(bot))
