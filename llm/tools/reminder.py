# MIT License
# Copyright (c) 2024 starpig1129

import logging
from typing import Optional, TYPE_CHECKING
 
from langchain_core.tools import tool
from typing import Any
from cogs.remind import ReminderCog
from function import func

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest


class ReminderTools:
    def __init__(self, runtime: "OrchestratorRequest"):
        self.runtime = runtime

    @tool
    async def set_reminder(
        self, time_str: str, message: str, user_id: Optional[int] = None
    ) -> str:
        """Reminder setting interface wrapped for LLM tools.

        - Relies on ReminderCog._set_reminder_logic for scheduling and validation.
        - All errors are reported via func.report_error.
        """
        logger = getattr(self.runtime, "logger", logging.getLogger(__name__))
        bot = getattr(self.runtime, "bot", None)
        if not bot:
            logger = logging.getLogger(__name__)
            logger.error("Bot instance not available in runtime.")
            return "Error: Bot instance not available."
        message_obj = getattr(self.runtime, "message", None)

        cog: Optional[ReminderCog] = bot.get_cog("ReminderCog")
        if not cog:
            msg = "Error: ReminderCog is not loaded."
            logger.error(msg)
            return msg

        # Determine target user
        try:
            if user_id is None:
                # If user_id is not specified, use the requester
                if message_obj and getattr(message_obj, "author", None):
                    target_user_id = message_obj.author.id
                else:
                    target_user_id = None
            else:
                target_user_id = user_id

            try:
                target_user = (
                    await bot.fetch_user(target_user_id)
                    if target_user_id is not None
                    else None
                )
            except Exception:
                # fetch_user may fail; use fallback name
                target_user = None

            channel = getattr(message_obj, "channel", None)
            guild_id = None
            guild_obj = getattr(message_obj, "guild", None)
            if guild_obj:
                guild_id = str(guild_obj.id)
            else:
                guild_id = "@me"

            logger.info(
                "Setting reminder",
                extra={"target_user_id": target_user_id, "guild": guild_id},
            )

            result = await cog._set_reminder_logic(
                channel=channel,
                target_user=target_user,
                time_str=time_str,
                message=message,
                guild_id=guild_id,
                interaction=None,
            )
            logger.info("Reminder scheduled", extra={"result": result})
            return result
        except Exception as e:  # pragma: no cover - orchestrator logic
            await func.report_error(e, f"set_reminder failed for user {user_id}")
            return f"Error: Failed to set reminder: {e}"