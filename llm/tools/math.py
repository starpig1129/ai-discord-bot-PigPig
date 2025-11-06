# MIT License
# Copyright (c) 2024 starpig1129

import logging
from typing import Optional
 
from langchain.tools import tool, ToolRuntime
from typing import Any, Optional
from function import func


class MathTools:
    def __init__(self, runtime: ToolRuntime):
        self.runtime = runtime

    @tool
    async def calculate_math(self, expression: str) -> str:
        """Math calculation tool wrapper delegated to MathCalculatorCog.

        - All errors are reported via func.report_error to follow project error handling standards.
        """
        context = self.runtime.context
        logger = getattr(context, "logger", logging.getLogger(__name__))
        logger.info("calculate_math called", extra={"expression": expression})
        bot = getattr(context, "bot", None)
        if not bot:
            logger.error("Bot instance not available in runtime.")
            return "Error: Bot instance not available."

        try:
            cog = bot.get_cog("MathCalculatorCog")
            if not cog:
                msg = "Error: MathCalculatorCog not found."
                logger.error(msg)
                return msg

            guild_id: Optional[str] = None
            message = getattr(context, "message", None)
            if message and getattr(message, "guild", None):
                guild_id = str(message.guild.id)

            result = await cog.calculate_math(expression, guild_id=guild_id)
            logger.info(
                "Delegated calculation completed",
                extra={"expression": expression, "result": result},
            )
            return result
        except Exception as e:  # pragma: no cover - external logic
            await func.report_error(
                e, f"Delegating math calculation for '{expression}' failed"
            )
            return (
                "An unexpected error occurred while processing the calculation: {e}"
            )