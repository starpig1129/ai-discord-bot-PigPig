# MIT License
# Copyright (c) 2024 starpig1129

from typing import Optional

from langchain.tools import tool, ToolRuntime
from typing import Any, Optional
from function import func

@tool
async def calculate_math(
    expression: str,
    context: ToolRuntime,
) -> str:
    """委派給 MathCalculatorCog 的數學計算工具封裝。

    - context 必須是第一個參數，與其他工具一致。
    - 所有錯誤透過 func.report_error 上報，遵守專案錯誤處理規範。
    """
    logger = context.logger
    logger.info("calculate_math called", extra={"expression": expression})

    try:
        cog = context.bot.get_cog("MathCalculatorCog")
        if not cog:
            msg = "Error: MathCalculatorCog not found."
            logger.error(msg)
            return msg

        guild_id: Optional[str] = None
        message = getattr(context, "message", None)
        if message and getattr(message, "guild", None):
            guild_id = str(message.guild.id)

        result = await cog.calculate_math(expression, guild_id=guild_id)
        logger.info("Delegated calculation completed", extra={"expression": expression, "result": result})
        return result
    except Exception as e:  # pragma: no cover - external logic
        await func.report_error(e, f"Delegating math calculation for '{expression}' failed")
        return f"An unexpected error occurred while processing the calculation: {e}"