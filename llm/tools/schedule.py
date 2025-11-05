# MIT License
# Copyright (c) 2024 starpig1129

from typing import Optional, Literal

from langchain_.tools import tool, ToolRuntime
from typing import Any, Optional, Literal
from cogs.schedule import ScheduleManager
from function import func

@tool
async def schedule_management(
    action: Literal["query", "update"],
    context: ToolRuntime,
    user_id: Optional[int] = None,
    query_type: Optional[Literal["full", "specific_time", "next"]] = None,
    time: Optional[str] = None,
    day: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """封裝的行事曆管理工具（LLM 工具專用）。

    - context 必須為第一參數。
    - 透過 ScheduleManager 處理查詢與更新。
    - 保持錯誤上報一致性（func.report_error）。
    """
    logger = context.logger
    author_id = getattr(context.message, "author", None)
    if user_id is None:
        try:
            target_user_id = context.message.author.id
        except Exception:
            target_user_id = None
    else:
        target_user_id = user_id

    cog: Optional[ScheduleManager] = context.bot.get_cog("ScheduleManager")
    if not cog:
        msg = "Error: ScheduleManager is not available."
        logger.error(msg)
        return msg

    try:
        if action == "query":
            if not query_type:
                return "Error: 'query_type' is required for the 'query' action."

            logger.info("Querying schedule", extra={"user_id": target_user_id, "query_type": query_type})
            return await cog._core_query_schedule(
                interaction_or_ctx=context.message,
                query_type=query_type,
                target_user_id=target_user_id,
                time=time,
                day=day,
            )

        if action == "update":
            if not all([day, time, description]):
                return "Error: 'day', 'time', and 'description' are required for the 'update' action."

            logger.info("Updating schedule", extra={"user_id": target_user_id, "day": day, "time": time})
            await cog._core_update_schedule(user_id=target_user_id, day=day, time=time, description=description)
            return f"Successfully updated schedule for user {target_user_id}."

        return f"Error: Invalid action '{action}'. Please use 'query' or 'update'."
    except Exception as e:  # pragma: no cover - external logic
        await func.report_error(e, f"Schedule management for user {target_user_id} failed")
        return f"An error occurred: {e}"