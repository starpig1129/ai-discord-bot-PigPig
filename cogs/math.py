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
from llm.utils.send_message import safe_edit_message
from function import func
import asyncio
from addons.logging import get_logger

# Module-level logger
log = get_logger(server_id="Bot", source=__name__)

class MathCalculatorCog(commands.Cog):
    """Cog for advanced mathematical calculations using SymPy."""

    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """Initialize LanguageManager when the cog is loaded."""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    async def calculate_math(self, expression: str, message_to_edit=None, guild_id: Optional[str] = None) -> str:
        """Parse and evaluate a mathematical expression, returning a localized result string."""
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)
        
        if message_to_edit is not None:
            processing_message = self.lang_manager.translate(
                guild_id, "commands", "math", "responses", "processing"
            ) if self.lang_manager else "Calculating..."
            await safe_edit_message(message_to_edit, processing_message)
        try:
            # Define allowed mathematical functions and constants
            allowed_functions = {
                # Basic and advanced math functions
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
                # Constants
                'pi': sympy.pi,
                'E': sympy.E,
                'e': sympy.E,
                'I': sympy.I,  # Imaginary unit
            }

            # Add necessary basic types to local_dict
            basic_types = {
                'Integer': sympy.Integer,
                'Float': sympy.Float,
                'Rational': sympy.Rational,
            }

            # Merge allowed functions and basic types
            local_dict = {**allowed_functions, **basic_types}

            # Define parsing transformations, supporting implicit multiplication etc.
            transformations = (
                standard_transformations +
                (implicit_multiplication_application,)
            )

            # Normalize expression
            expr_norm = unicodedata.normalize('NFKC', expression)

            # Standardize common symbol variants
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

            # Build allowed names list
            allowed_names = list(allowed_functions.keys()) + list(basic_types.keys())
            for _name in ['pi', 'E', 'e', 'I']:
                if _name not in allowed_names:
                    allowed_names.append(_name)
            allowed_names_sorted = sorted(set(allowed_names), key=len, reverse=True)
            tokens_pattern = r'(?:' + '|'.join(re.escape(n) for n in allowed_names_sorted) + r')'

            # Extract potential math expressions from mixed text
            pattern = re.compile(rf'(({tokens_pattern}|[0-9]+(?:\.[0-9]+)?|[()+\-*/,\s])+)', re.IGNORECASE)
            candidates = [m.group(1) for m in pattern.finditer(expr_norm)]

            # Filter valid candidates
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
                if self.lang_manager:
                    return self.lang_manager.translate(
                        guild_id, "commands", "math", "responses", "error_general", error="No calculable expression found"
                    )
                else:
                    return "Error: No calculable expression found."

            # Length limit
            if len(extracted) > 200:
                error_message = self.lang_manager.translate(
                    guild_id, "commands", "math", "responses", "error_too_long"
                ) if self.lang_manager else "Error: Expression too long."
                return error_message

            # Use extracted expression
            expression = extracted

            # Safely parse expression
            sympy_expr = parse_expr(
                expression,
                transformations=transformations,
                evaluate=True,
                local_dict=local_dict,
                global_dict={},  # Disable global_dict for safety
            )

            # Check for undefined functions
            from sympy.core.function import UndefinedFunction
            if sympy_expr.has(UndefinedFunction):
                error_message = self.lang_manager.translate(
                    guild_id, "commands", "math", "responses", "error_undefined_function"
                ) if self.lang_manager else "Error: Expression contains undefined functions."
                return error_message

            # Check for unsupported elements
            unsafe_types = (sympy.Symbol, sympy.Function)
            if sympy_expr.has(*unsafe_types):
                error_message = self.lang_manager.translate(
                    guild_id, "commands", "math", "responses", "error_unsupported_elements"
                ) if self.lang_manager else "Error: Expression contains unsupported elements."
                return error_message

            # Calculate result with 15 digits of precision
            result = sympy.N(sympy_expr, 15)

            # Format result string
            result_str = str(result)
            if '.' in result_str:
                result_str = result_str.rstrip('0').rstrip('.')

            log.info(f'Calculation completed: {expression} = {result_str}')
            
            result_message = self.lang_manager.translate(
                guild_id, "commands", "math", "responses", "result",
                expression=expression, result=result_str
            ) if self.lang_manager else f'Result: {expression} = {result_str}'
            
            return result_message
        except Exception as e:
            await func.report_error(e, "Calculation error in MathCalculatorCog")
            log.error("Calculation error", exception=e)
            error_message = self.lang_manager.translate(
                guild_id, "commands", "math", "responses", "error_general"
            ) if self.lang_manager else "Calculation error: Unable to parse or evaluate the expression."
            return error_message

async def setup(bot):
    """Set up the MathCalculatorCog."""
    await bot.add_cog(MathCalculatorCog(bot))
