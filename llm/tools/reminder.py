# MIT License
#
# Copyright (c) 2024 starpig1129
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Reminder tools for LLM integration.

This module provides LangChain-compatible tools for setting reminders
using the ReminderCog.
"""

import logging
from typing import Optional, TYPE_CHECKING

from langchain_core.tools import tool

from cogs.remind import ReminderCog
from function import func

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest


# Module-level logger
_logger = logging.getLogger(__name__)


class ReminderTools:
    """Container class for reminder management tools.
    
    This class holds the runtime context and provides factory methods
    to create tool instances bound to that context.
    
    Attributes:
        runtime: The orchestrator request containing bot, message, and logger.
    """

    def __init__(self, runtime: "OrchestratorRequest"):
        """Initializes ReminderTools with runtime context.
        
        Args:
            runtime: The orchestrator request object containing necessary context.
        """
        self.runtime = runtime

    def get_tools(self) -> list:
        """Returns a list of LangChain tools bound to this runtime.
        
        Returns:
            A list containing the set_reminder tool with runtime context.
        """
        runtime = self.runtime

        @tool
        async def set_reminder(
            time_str: str, message: str, user_id: Optional[int] = None
        ) -> str:
            """Sets a reminder for a user at a specified time.

            This tool schedules a reminder that will be sent to the specified user
            (or the message author if not specified) at the given time.

            Args:
                time_str: Time specification string (e.g., "10m", "2h", "tomorrow 3pm").
                    Supports various formats including relative times and absolute times.
                message: The reminder message content to be sent.
                user_id: Optional Discord user ID to remind. If not provided,
                    the reminder will be set for the message author.

            Returns:
                A success message with reminder details if scheduled successfully,
                or an error message describing what went wrong.
            """
            logger = getattr(runtime, "logger", _logger)
            
            # Retrieve bot instance from runtime
            bot = getattr(runtime, "bot", None)
            if not bot:
                logger.error("Bot instance not available in runtime.")
                return "Error: Bot instance not available."

            message_obj = getattr(runtime, "message", None)

            # Retrieve ReminderCog
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

                # Fetch user object
                try:
                    target_user = (
                        await bot.fetch_user(target_user_id)
                        if target_user_id is not None
                        else None
                    )
                except Exception as fetch_error:
                    # fetch_user may fail; log and use fallback
                    logger.warning(
                        "Failed to fetch user",
                        extra={
                            "user_id": target_user_id,
                            "error": str(fetch_error)
                        }
                    )
                    target_user = None

                # Extract channel and guild information
                channel = getattr(message_obj, "channel", None)
                guild_obj = getattr(message_obj, "guild", None)
                guild_id = str(guild_obj.id) if guild_obj else "@me"

                logger.info(
                    "Setting reminder",
                    extra={
                        "target_user_id": target_user_id,
                        "guild": guild_id,
                        "time_str": time_str
                    },
                )

                # Call reminder logic
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
                await func.report_error(
                    e, f"set_reminder failed for user {user_id}"
                )
                return f"Error: Failed to set reminder: {e}"

        return [set_reminder]
