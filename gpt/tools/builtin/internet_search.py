# MIT License
# Copyright (c) 2024 starpig1129

from typing import Literal
from gpt.tools.registry import tool
from gpt.tools.tool_context import ToolExecutionContext

@tool
async def internet_search(
    context: ToolExecutionContext,
    query: str,
    search_type: Literal["general", "image", "youtube", "url", "eat"]
) -> str:
    """
    Performs an internet search using various search types, acting as an interface to the InternetSearchCog.

    This tool delegates the core search logic to the 'InternetSearchCog', which handles
    different search types like general web search, image search, YouTube, reading URL content,
    and providing food recommendations ('eat').

    Args:
        context (ToolExecutionContext): The execution context, providing access to the bot,
                                        logger, and the original message.
        query (str): The search query, URL, or keyword for the search.
        search_type (Literal["general", "image", "youtube", "url", "eat"]): The type of search
                                                                           to perform.

    Returns:
        str: The result of the search operation. If the operation does not return a string
             (e.g., for image search which sends a file), a confirmation message is returned.
             Returns an error message if the required 'InternetSearchCog' is not found.
    """
    logger = context.logger
    logger.info(f"Delegating internet search of type '{search_type}' for query: '{query}'")

    cog = context.bot.get_cog("InternetSearchCog")
    if not cog:
        error_msg = "Error: InternetSearchCog not found. This is a critical error."
        logger.error(error_msg)
        return error_msg

    message = context.message
    message_to_edit = context.message_to_edit

    try:
        result = await cog.internet_search(
            ctx=message,
            query=query,
            search_type=search_type,
            message_to_edit=message_to_edit,
            guild_id=str(message.guild.id) if message.guild else None
        )
        
        if isinstance(result, str):
            return result
        
        # Handle cases where the cog sends a message directly (e.g., images, embeds)
        logger.info(f"Search of type '{search_type}' completed. The result was handled directly by the cog.")
        return f"Search for '{query}' of type '{search_type}' completed successfully."

    except Exception as e:
        logger.error(f"An error occurred while executing internet_search via cog: {e}", exc_info=True)
        return f"An unexpected error occurred during the search: {e}"
