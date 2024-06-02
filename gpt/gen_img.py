from diffusers import DiffusionPipeline
import torch
import discord
# 加載基礎模型和精細模型
base = DiffusionPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0",
    torch_dtype=torch.float16,
    variant="fp16",
    use_safetensors=True
)
base.to("cuda")

refiner = DiffusionPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-refiner-1.0",
    text_encoder_2=base.text_encoder_2,
    vae=base.vae,
    torch_dtype=torch.float16,
    use_safetensors=True,
    variant="fp16",
)
refiner.enable_model_cpu_offload()


async def generate_image(message_to_edit, message,prompt: str, n_steps: int = 40, high_noise_frac: float = 0.8):
    """
    使用 Stable Diffusion XL 模型生成圖像。

    Args:
        prompt (str): 用於生成圖像的提示文字。
        n_steps (int): 生成圖像的總步數。默認為 40。
        high_noise_frac (float): 在基礎模型上運行的步數比例。默認為 0.8。

    Returns:
        生成的圖像。
    """
    print(prompt)
    await message_to_edit.edit(content="畫畫中")
    # 定義步數和每個專家運行的步數比例 (80/20)
    high_noise_steps = int(n_steps * high_noise_frac)
    # 使用基礎模型生成初始圖像
    image = base(
        prompt=prompt,
        num_inference_steps=high_noise_steps,
        output_type="latent",
    ).images

    # 使用精細模型對初始圖像進行精細化
    image = refiner(
        prompt=prompt,
        num_inference_steps=n_steps - high_noise_steps,
        denoising_start=high_noise_frac,
        image=image,
    ).images[0]
    # 將生成的圖像保存為臨時文件
    with open("generated_image.png", "wb") as f:
        image.save(f, format="PNG")

    # 創建 discord.File 物件
    file = discord.File("generated_image.png")

    # 編輯消息並上傳圖像
    await message_to_edit.edit(content=f"完成{prompt}", attachments=[file])
    return None