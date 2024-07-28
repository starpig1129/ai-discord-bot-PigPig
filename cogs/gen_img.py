import discord
from discord import app_commands
from discord.ext import commands
import io
from PIL import Image
import torch
from diffusers import StableDiffusionInstructPix2PixPipeline, EulerAncestralDiscreteScheduler

class ImageGenerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model_id = "timbrooks/instruct-pix2pix"
        self.pipe = StableDiffusionInstructPix2PixPipeline.from_pretrained(self.model_id, torch_dtype=torch.float16, safety_checker=None)
        self.pipe.to("cuda:1")
        self.pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(self.pipe.scheduler.config)

    @app_commands.command(name="generate_image", description="生成一張圖片")
    @app_commands.describe(
        prompt="用於生成圖像的提示文字",
        n_steps="生成圖像的總步數（默認為10）"
    )
    async def generate_image_command(self, interaction: discord.Interaction, prompt: str, n_steps: int = 10):
        await interaction.response.defer(thinking=True)
        image = await self.generate_image(interaction.channel, prompt, n_steps)
        if image:
            file = discord.File(image, filename="generated_image.png")
            await interaction.followup.send(f"生成的圖片：{prompt}", file=file)
        else:
            await interaction.followup.send("生成圖片時發生錯誤。")

    async def generate_image(self, channel, prompt: str, n_steps: int = 10,message_to_edit: discord.Message = None):
        try:
            if message_to_edit:
                await message_to_edit.edit(content="畫畫中")
            else:
                message = await channel.send("畫畫中...")

            # 檢查是否有附加圖片
            if channel.last_message and channel.last_message.attachments:
                for attachment in channel.last_message.attachments:
                    if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        async with self.bot.session.get(attachment.url) as response:
                            image_data = await response.read()
                        image = Image.open(io.BytesIO(image_data)).convert('RGB')
                        break
                else:
                    image = Image.new("RGB", (512, 512), color="white")
            else:
                image = Image.new("RGB", (512, 512), color="white")

            images = self.pipe(prompt, image=image, num_inference_steps=n_steps, image_guidance_scale=1).images
            
            # 將生成的圖像保存為臨時文件
            image_buffer = io.BytesIO()
            images[0].save(image_buffer, format="PNG")
            image_buffer.seek(0)

            await message.edit(content=f"完成 {prompt}!")
            return image_buffer

        except Exception as e:
            print(f"生成圖片時發生錯誤：{str(e)}")
            return None

# async def setup(bot):
#     await bot.add_cog(ImageGenerationCog(bot))