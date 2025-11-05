# MIT License
# Copyright (c) 2024 starpig1129

import logging
from typing import Optional, Literal
 
from langchain.tools import tool, ToolRuntime
from typing import Any, Optional, Literal
from cogs.schedule import ScheduleManager
from function import func

@tool
async def schedule_management(
    action: Literal["query", "update"],
    runtime: ToolRuntime,  # type: ignore[arg-type]
    user_id: Optional[int] = None,
    query_type: Optional[Literal["full", "specific_time", "next"]] = None,
    time: Optional[str] = None,
    day: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Calendar management tool wrapper (for LLM tools).

    - runtime must be the ToolRuntime parameter.
    - Uses ScheduleManager to handle queries and updates.
    - Keeps error reporting consistent via func.report_error.
    """
    context = runtime.context
    logger = getattr(context, "logger", logging.getLogger(__name__))
    message_obj = getattr(context, "message", getattr(runtime, "message", None))
    author_id = getattr(message_obj, "author", None)
    if user_id is None:
        try:
            target_user_id = getattr(message_obj, "author", None).id if message_obj and getattr(message_obj, "author", None) else None
        except Exception:
            target_user_id = None
    else:
        target_user_id = user_id
    bot = getattr(runtime, "bot", None)
    if not bot:
        logger.error("Bot instance not available in runtime.")
        return "Error: Bot instance not available."

    cog: Optional[ScheduleManager] = bot.get_cog("ScheduleManager")
    if not cog:
        msg = "Error: ScheduleManager is not available."
        logger.error(msg)
        return msg

    try:
        if action == "query":
            if not query_type:
                return "Error: 'query_type' is required for the 'query' action."

            if target_user_id is None:
                return "Error: target user id is required for querying schedule."
            try:
                target_user_id_int = int(target_user_id)
            except Exception:
                return "Error: Invalid target user id."

            logger.info("Querying schedule", extra={"user_id": target_user_id_int, "query_type": query_type})
            return await cog._core_query_schedule(
                interaction_or_ctx=message_obj,
                query_type=query_type,
                target_user_id=target_user_id_int,
                time=time or "",
                day=day or "",
            )

        if action == "update":
            if not all([day, time, description]):
                return "Error: 'day', 'time', and 'description' are required for the 'update' action."

            if target_user_id is None:
                return "Error: target user id is required for updating schedule."
            try:
                target_user_id_int = int(target_user_id)
            except Exception:
                return "Error: Invalid target user id."

            logger.info("Updating schedule", extra={"user_id": target_user_id_int, "day": day, "time": time})
            await cog._core_update_schedule(user_id=target_user_id_int, day=day, time=time, description=description)
            return f"Successfully updated schedule for user {target_user_id_int}."

        return f"Error: Invalid action '{action}'. Please use 'query' or 'update'."
    except Exception as e:  # pragma: no cover - external logic
        await func.report_error(e, f"Schedule management for user {target_user_id} failed")
        return f"An error occurred: {e}"