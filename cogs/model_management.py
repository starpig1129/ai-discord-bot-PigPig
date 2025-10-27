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
from gpt.core.response_generator import get_model_and_tokenizer, set_model_and_tokenizer
import gc
from typing import Optional
from .language_manager import LanguageManager
from addons.settings import TOKENS

load_dotenv()

class ModelManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None
        self.tokens = TOKENS()  # 初始化 TOKENS 實例以獲取 BOT_OWNER_ID
        print("ModelManagement Cog initialized.")

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    def check_user(self, user_id: int) -> bool:
        """檢查使用者是否有權限使用這些命令"""
        print(f"Checking permissions for user_id: {user_id}")
        # 使用設定檔中的 BOT_OWNER_ID，如果設定檔中沒有則使用預設值
        bot_owner_id = getattr(self.tokens, 'bot_owner_id', 0)
        return user_id == bot_owner_id

    @app_commands.command(name="model_management", description="管理AI模型（開發者專用）")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="卸載模型", value="unload"),
            app_commands.Choice(name="載入模型", value="load")
        ]
    )
    async def model_management_command(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        # 檢查權限
        if not self.check_user(interaction.user.id):
            if not self.lang_manager:
                self.lang_manager = LanguageManager.get_instance(self.bot)
            
            guild_id = str(interaction.guild_id)
            error_msg = self.lang_manager.translate(
                guild_id, "system", "model_management", "errors", "permission_denied"
            ) if self.lang_manager else "您沒有權限執行此操作，僅限開發者使用。"
            
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)
        
        guild_id = str(interaction.guild_id)
        
        print(f"Developer-only command invoked by user: {interaction.user.id}, action: {action.value}")
        
        # 處理中訊息
        processing_msg = self.lang_manager.translate(
            guild_id, "system", "model_management", "status", "processing"
        ) if self.lang_manager else "正在處理模型操作..."
        
        await interaction.response.send_message(processing_msg)
        
        try:
            result = await self.execute_model_operation(action.value, guild_id)
            await interaction.edit_original_response(content=result)
        except Exception as e:
            func.report_error(e, f"executing model operation: {action.value}")
            error_msg = self.lang_manager.translate(
                guild_id, "commands", "model_management", "responses", "error", error=str(e)
            ) if self.lang_manager else f"執行操作時發生錯誤：{e}"
            await interaction.edit_original_response(content=error_msg)

    async def execute_model_operation(self, action: str, guild_id: str) -> str:
        """執行模型操作並返回翻譯後的結果訊息"""
        try:
            if action == "unload":
                # 卸載模型邏輯
                status_msg = self.lang_manager.translate(
                    guild_id, "system", "model_management", "status", "unloading"
                ) if self.lang_manager else "正在卸載模型..."
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
                    
                    result_msg = self.lang_manager.translate(
                        guild_id, "commands", "model_management", "responses", "model_unloaded"
                    ) if self.lang_manager else "模型已卸載。"
                    print("Model successfully unloaded.")
                    return result_msg
                else:
                    result_msg = self.lang_manager.translate(
                        guild_id, "commands", "model_management", "responses", "model_already_unloaded"
                    ) if self.lang_manager else "模型已經卸載或尚未載入。"
                    print("No model to unload or model already unloaded.")
                    return result_msg
                    
            elif action == "load":
                # 載入模型邏輯
                status_msg = self.lang_manager.translate(
                    guild_id, "system", "model_management", "status", "loading"
                ) if self.lang_manager else "正在載入模型..."
                print("Attempting to load model.")
                
                await self.reload_model()
                
                result_msg = self.lang_manager.translate(
                    guild_id, "commands", "model_management", "responses", "model_loaded"
                ) if self.lang_manager else "模型已載入。"
                print("Model successfully loaded.")
                return result_msg
                
            else:
                # 未知操作
                print(f"Invalid action received: {action}")
                completed_msg = self.lang_manager.translate(
                    guild_id, "commands", "model_management", "responses", "operation_completed"
                ) if self.lang_manager else "操作已完成。"
                return completed_msg
                
        except Exception as e:
            func.report_error(e, f"executing model operation: {action}")
            error_msg = self.lang_manager.translate(
                guild_id, "system", "model_management", "errors", "operation_failed", error=str(e)
            ) if self.lang_manager else f"模型操作失敗：{e}"
            raise Exception(error_msg)

    async def reload_model(self):
        """重新載入模型"""
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

    @model_management_command.error
    async def model_management_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """處理開發者專用命令的錯誤"""
        if isinstance(error, app_commands.CheckFailure):
            if not self.lang_manager:
                self.lang_manager = LanguageManager.get_instance(self.bot)
            
            guild_id = str(interaction.guild_id)
            error_msg = self.lang_manager.translate(
                guild_id, "system", "model_management", "errors", "permission_denied"
            ) if self.lang_manager else "您沒有權限執行此操作，僅限開發者使用。"
            
            if interaction.response.is_done():
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.response.send_message(error_msg, ephemeral=True)
        else:
            # 處理其他錯誤
            if not self.lang_manager:
                self.lang_manager = LanguageManager.get_instance(self.bot)
            
            guild_id = str(interaction.guild_id)
            error_msg = self.lang_manager.translate(
                guild_id, "system", "model_management", "errors", "operation_failed", error=str(error)
            ) if self.lang_manager else f"模型操作失敗：{error}"
            
            if interaction.response.is_done():
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.response.send_message(error_msg, ephemeral=True)

async def setup(bot):
    print("Setting up ModelManagement Cog.")
    await bot.add_cog(ModelManagement(bot))
    print("ModelManagement Cog added to bot.")
