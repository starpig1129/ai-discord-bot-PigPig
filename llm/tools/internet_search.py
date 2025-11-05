# MIT License
# Copyright (c) 2024 starpig1129

from typing import Literal
from langchain.tools import tool, ToolRuntime
from function import func

@tool
async def internet_search(
    query: str,
    context: ToolRuntime,
    search_type: Literal["general", "image", "youtube", "url", "eat"] = "general",
) -> str:
    """在 LLM 工具中封裝的網路搜尋接口。

    - 第一個參數為 ToolExecutionContext（與其他工具一致）。
    - 將實際工作委派給 InternetSearchCog。
    - 所有異常使用 func.report_error 上報。

    Args:
        context: 工具執行上下文。
        query: 搜尋字串或 URL。
        search_type: 搜尋類型。

    Returns:
        搜尋結果或錯誤說明字串。
    """
    logger = context.logger
    logger.info("internet_search called", extra={"query": query, "type": search_type})

    cog = context.bot.get_cog("InternetSearchCog")
    if not cog:
        msg = "Error: InternetSearchCog not found."
        logger.error(msg)
        return msg

    message = getattr(context, "message", None)
    message_to_edit = getattr(context, "message_to_edit", None)
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
        logger.info("internet_search completed and handled by cog", extra={"query": query})
        return f"Search for '{query}' ({search_type}) completed successfully."
    except Exception as e:  # pragma: no cover - external IO
        await func.report_error(e, f"Internet search for '{query}' of type '{search_type}' failed")
        return f"An unexpected error occurred during the search: {e}"
