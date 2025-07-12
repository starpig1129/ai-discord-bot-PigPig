# MIT License
# Copyright (c) 2024 starpig1129

from typing import Optional

from gpt.tools.registry import tool
from gpt.tools.tool_context import ToolExecutionContext
from cogs.remind import ReminderCog

@tool
async def set_reminder(
    context: ToolExecutionContext,
    time_str: str,
    message: str,
    user_id: Optional[int] = None
) -> str:
    """Schedules a reminder to be sent to a user at a specified time.

    This tool allows users to set reminders for future events. The time can be
    specified in a human-readable relative format (e.g., "in 15 minutes") or
    as an absolute timestamp. The bot will send a direct message to the user
    when the specified time arrives.

    Args:
        context (ToolExecutionContext): The execution context, providing access to the bot instance and message author.
        time_str (str): A string representing the time for the reminder.
                      Examples: "in 10 minutes", "1 hour later", "2 days",
                      "2024-12-31 20:00:00".
        message (str): The message content to be sent as the reminder.
        user_id (Optional[int]): The Discord user ID of the recipient. If not
                                 provided, the reminder is set for the user
                                 who initiated the command.

    Returns:
        str: A confirmation message indicating that the reminder has been
             successfully scheduled, including the target time. Returns an
             error message if the time format is invalid or in the past.
    """
    logger = context.logger
    bot = context.bot
    
    # 獲取 ReminderCog 實例
    cog: Optional[ReminderCog] = bot.get_cog("ReminderCog")
    if not cog:
        error_msg = "Error: ReminderCog is not loaded."
        logger.error(error_msg)
        return error_msg

    # 確定目標用戶
    target_user_id = user_id if user_id else context.message.author.id
    try:
        target_user = await bot.fetch_user(target_user_id)
    except Exception as e:
        error_msg = f"Error: Could not find user with ID {target_user_id}. Details: {e}"
        logger.error(error_msg)
        return error_msg

    # 獲取當前上下文的頻道和伺服器ID
    channel = context.message.channel
    guild_id = str(context.message.guild.id) if context.message.guild else "@me"

    logger.info(f"Attempting to set reminder for user {target_user.name} ({target_user_id}) in guild {guild_id}.")

    # 呼叫共用的核心邏輯
    result = await cog._set_reminder_logic(
        channel=channel,
        target_user=target_user,
        time_str=time_str,
        message=message,
        guild_id=guild_id,
        interaction=None  # LLM工具沒有互動對象
    )
    
    logger.info(f"Reminder logic executed for user {target_user_id}. Result: {result}")
    
    return result