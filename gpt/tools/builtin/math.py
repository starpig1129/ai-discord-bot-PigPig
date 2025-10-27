# MIT License
# Copyright (c) 2024 starpig1129

import sympy
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)
from typing import Union

from gpt.tools.registry import tool
from gpt.tools.tool_context import ToolExecutionContext
from function import func

@tool
async def calculate_math(
    context: ToolExecutionContext,
    expression: str,
) -> str:
    """Calculates the result of a mathematical expression by delegating to MathCalculatorCog.

    This tool serves as a lightweight interface that passes the mathematical
    expression to the core `calculate_math` method in `MathCalculatorCog`.
    The cog handles the actual parsing and computation, ensuring that the
    calculation logic is centralized and consistent.

    Args:
        context (ToolExecutionContext): The execution context for the tool,
            providing access to the bot instance and other resources.
        expression (str): The mathematical expression to be evaluated.
                          For example: "sqrt(16) + 2^3".

    Returns:
        str: The result of the calculation, which may be a number or an
             error message, as a string.
    """
    logger = context.logger
    try:
        # 從 context 獲取 MathCalculatorCog
        cog = context.bot.get_cog("MathCalculatorCog")
        if not cog:
            error_message = "MathCalculatorCog not found."
            logger.error(error_message)
            return error_message

        # 呼叫 cog 中的核心 calculate_math 方法
        # 注意：我們需要從 context 中獲取 guild_id
        guild_id = str(context.message.guild.id) if context.message and context.message.guild else None
        result = await cog.calculate_math(expression, guild_id=guild_id)
        
        logger.info(f'Delegated calculation for "{expression}". Result: {result}')
        return result

    except Exception as e:
        await func.report_error(e, f"Delegating math calculation for '{expression}' failed")
        return f"An unexpected error occurred while processing the calculation: {e}"