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
        ) -> str:
            """Performs an internet search based on the specified type.

            This tool supports multiple search types including general web search,
            YouTube video search, and specialized EAT (Expertise, Authoritativeness,
            Trustworthiness) search.

            Args:
                query: The search query string to process.
                search_type: The type of search to perform. Options are:
                    - "general": Standard web search (default)
                    - "youtube": YouTube video search
                    - "eat": Specialized search for authoritative content

            Returns:
                A string containing the search results, a success confirmation
                message, or an error description if the search failed.
            """
            logger = getattr(runtime, "logger", _logger)
            logger.info(
                "Tool 'internet_search' called",
                extra={"query": query, "search_type": search_type}
            )

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

            try:
                # Delegate to InternetSearchCog which handles all search type details
                result = await cog.internet_search(
                    ctx=message,
                    query=query,
                    search_type=search_type,
                    message_to_edit=message_to_edit,
                    guild_id=guild_id,
                )
                
                if isinstance(result, str):
                    return result

                # If cog directly sends messages (e.g., images or embeds),
                # return confirmation message
                logger.info(
                    "Internet search completed and handled by cog",
                    extra={"query": query, "search_type": search_type}
                )
                return (
                    f"Search for '{query}' ({search_type}) "
                    f"completed successfully."
                )
            except Exception as e:  # pragma: no cover - external IO
                await func.report_error(
                    e,
                    f"Internet search for '{query}' of type '{search_type}' failed"
                )
                return f"An unexpected error occurred during the search: {e}"

        return [internet_search]
