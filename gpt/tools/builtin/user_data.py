# MIT License
# Copyright (c) 2024 starpig1129

import json
from typing import Optional, Dict, Any

from gpt.tools.registry import tool
from gpt.tools.tool_context import ToolExecutionContext
from gpt.core.response_generator import generate_response
from function import func

def get_user_manager(context: ToolExecutionContext):
    """Helper function to safely get the user manager."""
    if hasattr(context.bot, 'memory_manager') and context.bot.memory_manager:
        return context.bot.memory_manager.db_manager.user_manager
    return None

@tool
async def manage_user_data(
    context: ToolExecutionContext,
    action: str,
    user_id: int,
    user_data: Optional[str] = None
) -> str:
    """Manages user data by reading or saving it.

    This tool serves as a unified interface for handling user data. It can
    either retrieve existing data for a user or save new/updated data.
    When saving, it intelligently merges the new data with any existing
    information.

    Args:
        context (ToolExecutionContext): The execution context, providing access to bot features.
        action (str): The operation to perform. Must be either 'read' or 'save'.
        user_id (int): The Discord user ID to manage data for.
        user_data (Optional[str]): The data to save. Required when action is 'save'.

    Returns:
        str: A message indicating the result of the operation.
    """
    logger = context.logger
    cog = context.bot.get_cog("UserDataCog")

    if not cog:
        return "Error: UserDataCog is not loaded."

    try:
        if action == 'read':
            logger.info(f"Reading data for user_id: {user_id}")
            return await cog._read_user_data(str(user_id), context)
        
        elif action == 'save':
            if user_data is None:
                return "Error: 'user_data' is required when action is 'save'."
            
            logger.info(f"Saving data for user_id: {user_id}")
            try:
                user = await context.bot.fetch_user(user_id)
                display_name = user.display_name
            except Exception:
                display_name = f"User_{user_id}"
                
            return await cog._save_user_data(str(user_id), display_name, user_data, context)
        
        else:
            return "Error: Invalid action. Please use 'read' or 'save'."

    except Exception as e:
        await func.report_error(e, f"Managing user data for {user_id} failed")
        return f"An unexpected error occurred: {e}"