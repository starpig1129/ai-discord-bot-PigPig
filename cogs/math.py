import discord
from discord import app_commands
from discord.ext import commands
import sympy

class MathCalculatorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="calculate", description="計算數學表達式")
    @app_commands.describe(expression="要計算的數學表達式")
    async def calculate_command(self, interaction: discord.Interaction, expression: str):
        await interaction.response.defer(thinking=True)
        result = await self.calculate_math(expression)
        await interaction.followup.send(result)

    async def calculate_math(self, expression: str,message_to_edit: discord.Message = None) -> str:
        try:
            if message_to_edit:
                await message_to_edit.edit(content="1 2 3...")
            # 將文字表達式轉換為 sympy 表達式對象
            sympy_expr = sympy.sympify(expression)
            # 計算表達式的值
            result = sympy.N(sympy_expr)
            return f'計算結果: {result}'
        except sympy.SympifyError as e:
            return f"無法計算: {str(e)}"
        except Exception as e:
            return f"計算錯誤: {str(e)}"

async def setup(bot):
    await bot.add_cog(MathCalculatorCog(bot))