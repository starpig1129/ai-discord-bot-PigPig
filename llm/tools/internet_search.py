# MIT License
# Copyright (c) 2024 starpig1129

import logging
from typing import Literal, TYPE_CHECKING
from langchain.tools import tool
from function import func

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest


class InternetSearchTools:
    def __init__(self, runtime: "OrchestratorRequest"):
        self.runtime = runtime

    @tool
    async def internet_search(
        self,
        query: str,
        search_type: Literal[
            "general", "image", "youtube", "url", "eat"
        ] = "general",
    ) -> str:
        """Internet search interface wrapped for LLM tools.

        - Delegates actual work to InternetSearchCog.
        - Reports all exceptions via func.report_error.

        Args:
            query: Search string or URL.
            search_type: Type of search.

        Returns:
            Search results or an error string.
        """
        logger = getattr(self.runtime, "logger", logging.getLogger(__name__))
        logger.info(
            "internet_search called", extra={"query": query, "type": search_type}
        )
        bot = getattr(self.runtime, "bot", None)
        if not bot:
            logger.error("Bot instance not available in runtime.")
            return "Error: Bot instance not available."

        cog = bot.get_cog("InternetSearchCog")
        if not cog:
            msg = "Error: InternetSearchCog not found."
            logger.error(msg)
            return msg

        message = getattr(self.runtime, "message", None)
        message_to_edit = getattr(self.runtime, "message_to_edit", None)
        guild_id = None
        if message and getattr(message, "guild", None):
            guild_id = str(message.guild.id)

        try:
            # InternetSearchCog.internet_search 內部處理各種 search_type 的細節
            result = await cog.internet_search(
                ctx=message,
                query=query,
                search_type=search_type,
                message_to_edit=message_to_edit,
                guild_id=guild_id,
            )
            if isinstance(result, str):
                return result

            # 若 cog 直接發送訊息（例如圖像或 embed），回傳確認訊息
            logger.info(
                "internet_search completed and handled by cog", extra={"query": query}
            )
            return f"Search for '{query}' ({search_type}) completed successfully."
        except Exception as e:  # pragma: no cover - external IO
            await func.report_error(
                e, f"Internet search for '{query}' of type '{search_type}' failed"
            )
            return f"An unexpected error occurred during the search: {e}"
