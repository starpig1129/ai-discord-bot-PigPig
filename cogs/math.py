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
import re
import unicodedata
from .language_manager import LanguageManager
from gpt.utils.discord_utils import safe_edit_message

class MathCalculatorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    async def calculate_math(self, expression: str, message_to_edit=None, guild_id: Optional[str] = None) -> str:
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)
        
        if message_to_edit is not None:
            processing_message = self.lang_manager.translate(
                guild_id, "commands", "calculate", "responses", "processing"
            ) if self.lang_manager else "計算中..."
            await safe_edit_message(message_to_edit, processing_message)
        try:
            # 限制表達式長度，防止過長的輸入
            # 長度檢查移至抽取後的表達式

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

            # 抽取與正規化數學表達式
            expr_norm = unicodedata.normalize('NFKC', expression)

            # 標準化常見符號變體
            for _src, _dst in {
                '×': '*',
                '∙': '*',
                '·': '*',
                '÷': '/',
                '–': '-',
                '—': '-',
                '−': '-',
                '^': '**',
            }.items():
                expr_norm = expr_norm.replace(_src, _dst)

            # 建立允許的名稱清單（函數與常數）
            allowed_names = list(allowed_functions.keys()) + list(basic_types.keys())
            for _name in ['pi', 'E', 'e', 'I']:
                if _name not in allowed_names:
                    allowed_names.append(_name)
            allowed_names_sorted = sorted(set(allowed_names), key=len, reverse=True)
            tokens_pattern = r'(?:' + '|'.join(re.escape(n) for n in allowed_names_sorted) + r')'

            # 從混合文字中擷取可能的數學表達式
            pattern = re.compile(rf'(({tokens_pattern}|[0-9]+(?:\.[0-9]+)?|[()+\-*/,\s])+)', re.IGNORECASE)
            candidates = [m.group(1) for m in pattern.finditer(expr_norm)]

            # 過濾有效候選（需包含數字或允許名稱）
            def _is_valid_candidate(s):
                s_strip = re.sub(r'^[=\s]+|[=\s]+$', '', s)
                if not s_strip:
                    return False
                if re.search(r'[0-9]', s_strip):
                    return True
                return re.search(tokens_pattern, s_strip, flags=re.IGNORECASE) is not None

            valid_candidates = [re.sub(r'^[=\s]+|[=\s]+$', '', c) for c in candidates if _is_valid_candidate(c)]
            extracted = max(valid_candidates, key=len) if valid_candidates else ''

            if not extracted:
                # 清楚錯誤：未找到可計算的表達式
                if self.lang_manager:
                    return self.lang_manager.translate(
                        guild_id, "responses", "error", error="未找到可計算的表達式"
                    )
                else:
                    return "錯誤：未找到可計算的表達式。"

            # 長度限制（以抽取後的表達式為準）
            if len(extracted) > 200:
                error_message = self.lang_manager.translate(
                    guild_id, "commands", "calculate", "responses", "error_too_long"
                ) if self.lang_manager else "錯誤：表達式過長，請縮短後再試。"
                return error_message

            # 使用抽取後的表達式
            expression = extracted

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




