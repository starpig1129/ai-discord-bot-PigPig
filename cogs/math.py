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
import sympy
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)
from typing import Optional
from .language_manager import LanguageManager

class MathCalculatorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    @app_commands.command(name="calculate", description="計算數學表達式")
    @app_commands.describe(expression="要計算的數學表達式")
    async def calculate_command(self, interaction: discord.Interaction, expression: str):
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)
        
        await interaction.response.defer(thinking=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        result = await self.calculate_math(expression, guild_id=guild_id)
        await interaction.followup.send(result)

    async def calculate_math(self, expression: str, message_to_edit=None, guild_id: Optional[str] = None) -> str:
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)
        
        if message_to_edit is not None:
            processing_message = self.lang_manager.translate(
                guild_id, "commands", "calculate", "responses", "processing"
            ) if self.lang_manager else "計算中..."
            await message_to_edit.edit(content=processing_message)
        try:
            # 限制表達式長度，防止過長的輸入
            if len(expression) > 200:
                error_message = self.lang_manager.translate(
                    guild_id, "commands", "calculate", "responses", "error_too_long"
                ) if self.lang_manager else "錯誤：表達式過長，請縮短後再試。"
                return error_message

            # 定義允許的數學函數和常數
            allowed_functions = {
                # 基本和高等數學函數
                'sin': sympy.sin,
                'cos': sympy.cos,
                'tan': sympy.tan,
                'cot': sympy.cot,
                'sec': sympy.sec,
                'csc': sympy.csc,
                'asin': sympy.asin,
                'acos': sympy.acos,
                'atan': sympy.atan,
                'acot': sympy.acot,
                'sinh': sympy.sinh,
                'cosh': sympy.cosh,
                'tanh': sympy.tanh,
                'coth': sympy.coth,
                'asinh': sympy.asinh,
                'acosh': sympy.acosh,
                'atanh': sympy.atanh,
                'ln': sympy.ln,
                'log': sympy.log,
                'exp': sympy.exp,
                'sqrt': sympy.sqrt,
                'Abs': sympy.Abs,
                'floor': sympy.floor,
                'ceiling': sympy.ceiling,
                'factorial': sympy.factorial,
                'gamma': sympy.gamma,
                'zeta': sympy.zeta,
                'erf': sympy.erf,
                # 常數
                'pi': sympy.pi,
                'E': sympy.E,
                'e': sympy.E,
                'I': sympy.I,  # 虛數單位
            }

            # 添加必要的基礎類型到 local_dict
            basic_types = {
                'Integer': sympy.Integer,
                'Float': sympy.Float,
                'Rational': sympy.Rational,
            }

            # 合併允許的函數和基礎類型
            local_dict = {**allowed_functions, **basic_types}

            # 定義解析轉換規則，支持隱式乘法等
            transformations = (
                standard_transformations +
                (implicit_multiplication_application,)
            )

            # 安全地解析表達式
            sympy_expr = parse_expr(
                expression,
                transformations=transformations,
                evaluate=True,
                local_dict=local_dict,
                global_dict={},  # 禁用 global_dict
            )

            # 檢查解析結果是否包含未定義的函數
            from sympy.core.function import UndefinedFunction
            if sympy_expr.has(UndefinedFunction):
                error_message = self.lang_manager.translate(
                    guild_id, "commands", "calculate", "responses", "error_undefined_function"
                ) if self.lang_manager else "錯誤：表達式包含未定義的函數。"
                return error_message

            # 檢查解析結果是否包含不安全的類型
            unsafe_types = (sympy.Symbol, sympy.Function)
            if sympy_expr.has(*unsafe_types):
                error_message = self.lang_manager.translate(
                    guild_id, "commands", "calculate", "responses", "error_unsupported_elements"
                ) if self.lang_manager else "錯誤：表達式包含不支持的元素。"
                return error_message

            # 計算結果，設定精度為 15 位小數
            result = sympy.N(sympy_expr, 15)

            # 格式化結果，去除多餘的小數點和零
            result_str = str(result)
            if '.' in result_str:
                result_str = result_str.rstrip('0').rstrip('.')

            print(f'計算結果: {expression} = {result_str}')
            
            # 使用翻譯系統格式化結果訊息
            result_message = self.lang_manager.translate(
                guild_id, "commands", "calculate", "responses", "result",
                expression=expression, result=result_str
            ) if self.lang_manager else f'計算結果: {expression} = {result_str}'
            
            return result_message
        except Exception as e:
            print(f"計算錯誤: {str(e)}")
            error_message = self.lang_manager.translate(
                guild_id, "commands", "calculate", "responses", "error_general"
            ) if self.lang_manager else "計算錯誤：無法解析或計算該表達式。"
            return error_message

async def setup(bot):
    await bot.add_cog(MathCalculatorCog(bot))




