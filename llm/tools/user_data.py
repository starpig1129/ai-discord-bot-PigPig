# MIT License
# Copyright (c) 2024 starpig1129

import logging
from typing import Optional, Any
 
from langchain.tools import tool, ToolRuntime
from function import func


class UserDataTools:
    def __init__(self, runtime: ToolRuntime):
        self.runtime = runtime

    @tool
    async def manage_user_data(
        self, action: str, user_id: int, user_data: Optional[str] = None
    ) -> str:
        """User data management tool wrapper (read / save).

        - 'read' returns user data (handled by UserDataCog).
        - 'save' stores data and merges with existing data.
        - All errors are reported via func.report_error to ensure consistent logging.
        """
        context = self.runtime.context
        logger = getattr(context, "logger", logging.getLogger(__name__))
        bot = getattr(context, "bot", None)
        if not bot:
            logger.error("Bot instance not available in runtime.")
            return "Error: Bot instance not available."
        cog = bot.get_cog("UserDataCog")

        if not cog:
            msg = "Error: UserDataCog is not loaded."
            logger.error(msg)
            return msg

        try:
            if action == "read":
                logger.info("Reading user data", extra={"user_id": user_id})
                return await cog._read_user_data(str(user_id), context)

            if action == "save":
                if user_data is None:
                    return (
                        "Error: 'user_data' is required when action is 'save'."
                    )

                logger.info("Saving user data", extra={"user_id": user_id})
                try:
                    # prefer bot.fetch_user; context may not contain bot
                    user = await bot.fetch_user(user_id)
                    display_name = getattr(
                        user, "display_name", f"User_{user_id}"
                    )
                except Exception:
                    display_name = f"User_{user_id}"

                return await cog._save_user_data(
                    str(user_id), display_name, user_data, context
                )

            return "Error: Invalid action. Please use 'read' or 'save'."
        except Exception as e:  # pragma: no cover - external logic
            await func.report_error(
                e, f"Managing user data for {user_id} failed"
            )
            return f"An unexpected error occurred: {e}"