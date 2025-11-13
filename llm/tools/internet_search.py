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

"""Internet search tools for LLM integration.

This module provides LangChain-compatible tools for performing various types
of internet searches using the InternetSearchCog.
"""

import logging
import os
import time
from typing import Literal, TYPE_CHECKING

from langchain_core.tools import tool

from function import func

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest


# Module-level logger
_logger = logging.getLogger(__name__)


class InternetSearchTools:
    """Container class for internet search tools.

    This class holds the runtime context and provides factory methods
    to create tool instances bound to that context.

    Attributes:
        runtime: The orchestrator request containing bot, message, and logger.
    """

    def __init__(self, runtime: "OrchestratorRequest"):
        """Initializes InternetSearchTools with runtime context.

        Args:
            runtime: The orchestrator request object containing necessary context.
        """
        self.runtime = runtime

    def get_tools(self) -> list:
        """Returns a list of LangChain tools bound to this runtime.

        Returns:
            A list containing the internet_search tool with runtime context.
        """
        runtime = self.runtime

        @tool
        async def internet_search(
            query: str,
            search_type: Literal[
                "general", "youtube", "eat"
            ] = "general",
            search_instructions: str = ""
        ) -> str:
            """Performs an internet search and records Gemini grounding usage.
    
            Guidance for model callers:
            - This tool will invoke a grounding-enabled search agent (Gemini) when an API key
              is available. The model may therefore provide *search instructions* to influence
              the agent behaviour (for example: "prefer official sources", "only use sources
              from the last 2 years", "return output as JSON with keys answer/sources/highlights").
            - If you supply structured search instructions, pass them via the 'search_instructions'
              parameter. The tool will prepend those instructions to the user's query when
              delegating to the cog.
    
            Args:
                query: The search query string to process.
                search_type: The type of search to perform.
                search_instructions: Optional short instructions for the grounding agent.
    
            Returns:
                A string result from the cog or a confirmation message. When possible the
                returned string is prefixed with provider and duration metadata for observability.
            """
            logger = getattr(runtime, "logger", _logger)
            logger.info("Tool 'internet_search' called", extra={"query": query, "search_type": search_type, "search_instructions": bool(search_instructions)})
    
            # Determine preferred provider based on environment
            gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            preferred_provider = "gemini" if gemini_key else "selenium"
            logger.debug("Preferred search provider determined", extra={"preferred_provider": preferred_provider})
    
            # Retrieve bot instance from runtime
            bot = getattr(runtime, "bot", None)
            if not bot:
                logger.error("Bot instance not available in runtime.")
                return "Error: Bot instance not available."
    
            # Retrieve InternetSearchCog
            cog = bot.get_cog("InternetSearchCog")
            if not cog:
                msg = "Error: InternetSearchCog not found."
                logger.error(msg)
                return msg
    
            # Extract message and guild information
            message = getattr(runtime, "message", None)
            message_to_edit = getattr(runtime, "message_to_edit", None)
            guild_id = None
            if message and getattr(message, "guild", None):
                guild_id = str(message.guild.id)
    
            # If the higher-level model provided search instructions, prepend them to the query
            query_to_pass = f"{search_instructions}\n\n{query}" if search_instructions else query
    
            start_ts = time.time()
            try:
                # Pass through to the cog which prefers Gemini grounding internally.
                result = await cog.internet_search(
                    ctx=message,
                    query=query_to_pass,
                    search_type=search_type,
                    message_to_edit=message_to_edit,
                    guild_id=guild_id,
                )
    
                duration = time.time() - start_ts
                used_provider = preferred_provider  # best-effort; cog makes final decision
                logger.info("Internet search finished", extra={"query": query, "search_type": search_type, "duration_s": duration, "used_provider": used_provider})
    
                if isinstance(result, str):
                    # Attach metadata about provider to the returned string for observability
                    return f"[provider={used_provider} duration={duration:.2f}s] {result}"
    
                # If cog handled messaging (embeds, views), return confirmation
                logger.info("Internet search completed and handled by cog", extra={"query": query, "search_type": search_type})
                return f"[provider={used_provider} duration={duration:.2f}s] Search for '{query}' ({search_type}) completed successfully."
            except Exception as e:  # pragma: no cover - external IO
                duration = time.time() - start_ts
                await func.report_error(e, f"Internet search for '{query}' of type '{search_type}' failed after {duration:.2f}s")
                logger.exception("Internet search tool failed", exc_info=e)
                return f"An unexpected error occurred during the search: {e}"

        return [internet_search]
