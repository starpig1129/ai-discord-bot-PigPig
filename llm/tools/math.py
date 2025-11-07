# MIT License
#
# Copyright (c) 2024 starpig1129
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Math calculation tools for LLM integration.

This module provides LangChain-compatible tools for performing mathematical
calculations using the MathCalculatorCog.
"""

import logging
from typing import Optional, TYPE_CHECKING

from langchain_core.tools import tool

from function import func

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest


# Module-level logger
_logger = logging.getLogger(__name__)


class MathTools:
    """Container class for mathematical calculation tools.
    
    This class holds the runtime context and provides factory methods
    to create tool instances bound to that context.
    
    Attributes:
        runtime: The orchestrator request containing bot, message, and logger.
    """

    def __init__(self, runtime: "OrchestratorRequest"):
        """Initializes MathTools with runtime context.
        
        Args:
            runtime: The orchestrator request object containing necessary context.
        """
        self.runtime = runtime

    def get_tools(self) -> list:
        """Returns a list of LangChain tools bound to this runtime.
        
        Returns:
            A list containing the calculate_math tool with runtime context.
        """
        runtime = self.runtime
        
        @tool
        async def calculate_math(expression: str) -> str:
            """Performs mathematical calculations on a given expression.

            This tool evaluates mathematical expressions and returns the result.
            It delegates the actual calculation to the MathCalculatorCog.

            Args:
                expression: A mathematical expression to evaluate (e.g., "2 + 2",
                    "sqrt(16)", "sin(pi/2)").

            Returns:
                The calculation result as a string, or an error message if the
                calculation failed.
            """
            logger = getattr(runtime, "logger", _logger)
            logger.info("calculate_math called", extra={"expression": expression})

            # Retrieve bot instance from runtime
            bot = getattr(runtime, "bot", None)
            if not bot:
                logger.error("Bot instance not available in runtime.")
                return "Error: Bot instance not available."

            try:
                # Retrieve MathCalculatorCog
                cog = bot.get_cog("MathCalculatorCog")
                if not cog:
                    msg = "Error: MathCalculatorCog not found."
                    logger.error(msg)
                    return msg

                # Extract guild_id from message context
                guild_id: Optional[str] = None
                message = getattr(runtime, "message", None)
                if message and getattr(message, "guild", None):
                    guild_id = str(message.guild.id)

                # Perform calculation
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
                    f"An unexpected error occurred while processing the "
                    f"calculation: {e}"
                )

        return [calculate_math]
