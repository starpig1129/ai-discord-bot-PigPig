# MIT License
# Copyright (c) 2024 starpig1129

from typing import Optional, Literal

from gpt.tools.registry import tool
from gpt.tools.tool_context import ToolExecutionContext
from cogs.schedule import ScheduleManager
import function as func

@tool
async def schedule_management(
    context: ToolExecutionContext,
    action: Literal["query", "update"],
    user_id: Optional[int] = None,
    query_type: Optional[Literal["full", "specific_time", "next"]] = None,
    time: Optional[str] = None,
    day: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Manages user schedules, allowing for querying, and updating events.

    This tool serves as an interface to the bot's scheduling system. It can be
    used to check existing schedules or to add new events to a user's calendar.
    All schedule data is associated with a user's Discord ID.

    Args:
        context (ToolExecutionContext): The execution context, providing access
            to the bot, logger, and message details.
        action (Literal["query", "update"]): The operation to perform.
            - 'query': Retrieves schedule information.
            - 'update': Adds a new event to the schedule.
        user_id (Optional[int]): The Discord user ID to perform the action on.
            Defaults to the message author's ID if not provided.
        query_type (Optional[Literal["full", "specific_time", "next"]]):
            Required when action is 'query'. Defines the type of query.
            - 'full': Get the entire schedule.
            - 'specific_time': Find events at a specific time.
            - 'next': Find the next upcoming event.
        time (Optional[str]): The time for the event or query, usually in
            'HH:MM-HH:MM' or 'YYYY-MM-DD HH:MM:SS' format. Required for
            'specific_time' queries and 'update' actions.
        day (Optional[str]): The day of the week (e.g., "Monday"). Required
            for 'update' actions. Can be used with 'specific_time' queries.
        description (Optional[str]): A description of the event. Required for
            'update' actions.

    Returns:
        str: A confirmation message, the requested schedule information, or an
             error message if the operation fails.
    """
    logger = context.logger
    target_user_id = user_id if user_id else context.message.author.id
    
    cog: Optional[ScheduleManager] = context.bot.get_cog("ScheduleManager")
    if not cog:
        return "Error: ScheduleManager is not available."

    try:
        if action == "query":
            if not query_type:
                return "Error: 'query_type' is required for the 'query' action."
            
            logger.info(f"Querying schedule for user_id: {target_user_id} with query_type: {query_type}")
            return await cog._core_query_schedule(
                interaction_or_ctx=context.message,
                query_type=query_type,
                target_user_id=target_user_id,
                time=time,
                day=day
            )
        
        elif action == "update":
            if not all([day, time, description]):
                return "Error: 'day', 'time', and 'description' are required for the 'update' action."
            
            logger.info(f"Updating schedule for user_id: {target_user_id}")
            await cog._core_update_schedule(
                user_id=target_user_id,
                day=day,
                time=time,
                description=description
            )
            return f"Successfully updated schedule for user {target_user_id}."
            
        else:
            return f"Error: Invalid action '{action}'. Please use 'query' or 'update'."

    except Exception as e:
        await func.func.report_error(e, f"Schedule management for user {target_user_id} failed")
        return f"An error occurred: {e}"