import discord
import PIL
import requests
import torch
import aiohttp
import io
from PIL import Image
from diffusers import StableDiffusionInstructPix2PixPipeline, EulerAncestralDiscreteScheduler


async def generate_image(message_to_edit, message,prompt: str, n_steps: int = 10):
    """
    使用 Stable Diffusion XL 模型生成圖像。

    Args:
        prompt (str): 用於生成圖像的提示文字。
        n_steps (int): 生成圖像的總步數。默認為 40。

    Returns:
        生成的圖像。
    """
    print(prompt)
    await message_to_edit.edit(content="畫畫中")
    model_id = "timbrooks/instruct-pix2pix"
    pipe = StableDiffusionInstructPix2PixPipeline.from_pretrained(model_id, torch_dtype=torch.float16, safety_checker=None)
    pipe.to("cuda:1")
    pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
    if message.attachments:
        await message_to_edit.edit(content="我看看")
        for attachment in message.attachments:
            if attachment.filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as response:
                        image_data = await response.read()
        image = Image.open(io.BytesIO(image_data)).convert('RGB')
    else:
        # 創建一個白色的起始圖像
        image = Image.new("RGB", (512, 512), color="white")
    images = pipe(prompt, image=image, num_inference_steps=n_steps, image_guidance_scale=1).images
    images[0]
    # 將生成的圖像保存為臨時文件
    with open("generated_image.png", "wb") as f:
        image.save(f, format="PNG")

    # 創建 discord.File 物件
    file = discord.File("generated_image.png")

    # 編輯消息並上傳圖像
    await message_to_edit.edit(content=f"完成{prompt}!", attachments=[file])
    return None