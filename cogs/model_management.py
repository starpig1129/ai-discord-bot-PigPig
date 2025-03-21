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
from discord.ext import commands
from discord import app_commands
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, AutoModel
import os
from dotenv import load_dotenv
from gpt.gpt_response_gen import get_model_and_tokenizer, set_model_and_tokenizer
import gc
load_dotenv()

class ModelManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("ModelManagement Cog initialized.")

    @staticmethod
    def check_user(user_id: int) -> bool:
        # 檢查使用者是否有權限使用這些命令
        print(f"Checking permissions for user_id: {user_id}")
        return user_id in [597028717948043274]  # 用戶ID

    @app_commands.command(name="developer_only", description="開發者專用")
    @app_commands.check(lambda interaction: ModelManagement.check_user(interaction.user.id))
    @app_commands.choices(
        action=[
            app_commands.Choice(name="卸載模型", value="unload_model"),
            app_commands.Choice(name="加載模型", value="load_model")
        ]
    )
    async def developer_only(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        print(f"Developer-only command invoked by user: {interaction.user.id}, action: {action.value}")
        actions = {
            "unload_model": self.unload_model,
            "load_model": self.load_model,
        }
        
        if action.value not in actions:
            print(f"Invalid action received: {action.value}")
            await interaction.response.send_message(f"Invalid action: {action.value}")
            return

        await interaction.response.defer()
        await actions[action.value](interaction)

    async def unload_model(self, interaction: discord.Interaction):
        print("Attempting to unload model.")
        model, tokenizer = get_model_and_tokenizer()
        if model is not None:
            print("Unloading model and tokenizer.")
            set_model_and_tokenizer(None, None)
            del model
            del tokenizer
            gc.collect()
            torch.cuda.empty_cache()
            set_model_and_tokenizer(None, None)
            await interaction.followup.send("模型已卸載。")
            print("Model successfully unloaded.")
        else:
            await interaction.followup.send("模型已經卸載或尚未加載。")
            print("No model to unload or model already unloaded.")

    async def load_model(self, interaction: discord.Interaction):
        print("Attempting to load model.")
        await self.reload_model()
        await interaction.followup.send("模型已加載。")
        print("Model successfully loaded.")

    async def reload_model(self):
        model_name = os.getenv("MODEL_NAME", "openbmb/MiniCPM-o-2_6")
        print(f"Loading model with name: {model_name}")
        
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=True
        )
        
        model = AutoModel.from_pretrained(
            model_name,
            trust_remote_code=True,
            attn_implementation='sdpa',
            torch_dtype=torch.bfloat16
        ).eval().cuda()
        
        # 初始化 TTS 模組
        model.init_tts()
        model.tts.float()  # 避免某些 PyTorch 版本的兼容性問題
        
        set_model_and_tokenizer(model, tokenizer)
        print("Model and tokenizer set.")

async def setup(bot):
    print("Setting up ModelManagement Cog.")
    await bot.add_cog(ModelManagement(bot))
    print("ModelManagement Cog added to bot.")
