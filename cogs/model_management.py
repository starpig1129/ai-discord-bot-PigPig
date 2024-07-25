import discord
from discord.ext import commands
from discord import app_commands
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig,AutoModel
import os
from dotenv import load_dotenv
from gpt.gpt_response_gen import get_model_and_tokenizer,set_model_and_tokenizer
from gpt.vqa import get_VQA_and_tokenizer,set_VQA_and_tokenizer
import gc
load_dotenv()

class ModelManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    @staticmethod
    def check_user(user_id: int) -> bool:
        # 檢查使用者是否有權限使用這些命令
        return user_id in [597028717948043274]  # 用戶ID

    @app_commands.command(name="unload_llm", description="卸載語言模型")
    @app_commands.check(lambda interaction: ModelManagement.check_user(interaction.user.id))
    async def unload_LLM(self, interaction: discord.Interaction):
        model, tokenizer = get_model_and_tokenizer()
        if model is not None:
            set_model_and_tokenizer(None, None)
            del model
            del tokenizer
            gc.collect()
            torch.cuda.empty_cache()
            set_model_and_tokenizer(None, None)
            await interaction.response.send_message("語言模型已卸載。")
        else:
            await interaction.response.send_message("模型已經卸載或尚未加載。")

    @app_commands.command(name="load_llm", description="加載語言模型")
    @app_commands.check(lambda interaction: ModelManagement.check_user(interaction.user.id))
    async def load_LLM(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.reload_LLM()
        await interaction.followup.send("語言模型已加載。")
    async def reload_LLM(self):
        model_name = os.getenv("LLM_MODEL_NAME")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype="float16",
            bnb_4bit_use_double_quant=False
        )
        tokenizer = AutoTokenizer.from_pretrained(
            model_name, 
            use_fast=False,
            trust_remote_code=True,
            skip_special_tokens=True
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_name, 
            torch_dtype=torch.bfloat16,
            quantization_config=bnb_config,
            device_map={"":0},
            attn_implementation='sdpa',
            trust_remote_code=True,
        )
        model.config.use_cache = False
        model.bfloat16()
        model.eval()
        
        set_model_and_tokenizer(model, tokenizer)
        
    @app_commands.command(name="unload_vqa", description="卸載VQA模型")
    @app_commands.check(lambda interaction: ModelManagement.check_user(interaction.user.id))
    async def unload_model(self, interaction: discord.Interaction):
        model, tokenizer = get_VQA_and_tokenizer()
        if model is not None:
            set_VQA_and_tokenizer(None, None)
            del model
            del tokenizer
            gc.collect()
            torch.cuda.empty_cache()
            set_VQA_and_tokenizer(None, None)
            await interaction.response.send_message("VQA模型已卸載。")
        else:
            await interaction.response.send_message("模型已經卸載或尚未加載。")

    @app_commands.command(name="load_vqa", description="加載VQA模型")
    @app_commands.check(lambda interaction: ModelManagement.check_user(interaction.user.id))
    async def load_model(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.reload_vqa_model()
        await interaction.followup.send("VQA模型已加載。")
    async def reload_vqa_model(self):
        vqa_model_name = os.getenv("VQA_MODEL_NAME")
        model = AutoModel.from_pretrained(vqa_model_name, trust_remote_code=True)
        tokenizer = AutoTokenizer.from_pretrained(vqa_model_name, trust_remote_code=True)
        model.eval()
        set_VQA_and_tokenizer(model, tokenizer)    

async def setup(bot):
    await bot.add_cog(ModelManagement(bot))