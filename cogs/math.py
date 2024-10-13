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
import re

class MathCalculatorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.dangerous_functions = ["exec", "eval", "system", "import", "open"]

    @app_commands.command(name="calculate", description="計算數學表達式")
    @app_commands.describe(expression="要計算的數學表達式")
    async def calculate_command(self, interaction: discord.Interaction, expression: str):
        await interaction.response.defer(thinking=True)
        result = await self.calculate_math(expression)
        await interaction.followup.send(result)

    async def calculate_math(self, expression: str ,message_to_edit=None) -> str:
        if message_to_edit is not None:
            await message_to_edit.edit(content='123...')
        try:
            # Sanitize input
            expression = self.sanitize_input(expression)
            # Convert to sympy expression
            sympy_expr = sympy.sympify(expression)
            # Calculate and return result
            result = sympy.N(sympy_expr)
            print(f'計算結果: {expression}={result}')
            return f'計算結果: {expression}={result}'
        except sympy.SympifyError as e:
            print(f"無法計算: {str(e)}")
            return f"無法計算: {str(sympy_expr)}"
        except Exception as e:
            print(f"無法計算: {str(e)}")
            return f"計算錯誤: {str(sympy_expr)}"

    def sanitize_input(self, expression):
        # Remove dangerous functions
        for func in self.dangerous_functions:
            expression = expression.replace(func, "")
        # Remove potentially harmful characters (adjust as needed)
        expression = re.sub(r"[^0-9a-zA-Z+\-*/(). ]", "", expression)
        return expression

async def setup(bot):
    await bot.add_cog(MathCalculatorCog(bot))
