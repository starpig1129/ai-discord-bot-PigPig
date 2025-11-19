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

"""User memory management tools for LLM integration.

This module provides LangChain-compatible tools for managing user personal
memory (procedural memory) through the UserDataCog.
"""

from addons.logging import get_logger
from typing import Optional, Any, TYPE_CHECKING, Union, cast

import discord
from langchain_core.tools import tool

from function import func
from cogs.userdata import UserDataCog

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest


# Module-level logger
_logger = get_logger(server_id="Bot", source="llm.tools.user_data")


class UserMemoryTools:
    """Container class for user memory management tools.
    
    This class provides tools for a LangChain Agent to manage a user's
    personal memory (also known as procedural memory). It encapsulates
    the UserDataCog's functionality, allowing the Agent to read or save
    specific preferences, facts, or interaction rules that the user has
    previously asked the bot to remember.
    
    Attributes:
        runtime: The orchestrator request containing bot, message, and logger.
        logger: Logger instance for this tool.
    """

    def __init__(self, runtime: "OrchestratorRequest"):
        """Initializes UserMemoryTools with runtime context.
        
        Args:
            runtime: The orchestrator request object containing necessary context
                (bot, logger, message, etc.).
        """
        self.runtime = runtime
        self.logger = getattr(self.runtime, "logger", _logger)

    def _get_bot(self) -> Optional[Any]:
        """Safely retrieves the bot instance from the runtime.
        
        Returns:
            The bot instance if available, None otherwise.
        """
        bot = getattr(self.runtime, "bot", None)
        if not bot:
            self.logger.error("Bot instance not available in runtime.")
        return bot

    def _get_cog(self) -> Optional[UserDataCog]:
        """Safely retrieves the UserDataCog.
        
        Returns:
            The UserDataCog instance if available, None otherwise.
        """
        bot = self._get_bot()
        if not bot:
            return None
        
        cog = bot.get_cog("UserDataCog")
        if not cog:
            self.logger.error("UserDataCog is not loaded.")
            return None
        
        return cog

    def get_tools(self) -> list:
        """Returns a list of LangChain tools bound to this runtime.
        
        Returns:
            A list containing user memory management tools with runtime context.
        """
        runtime = self.runtime
        logger = self.logger
        get_bot = self._get_bot
        get_cog = self._get_cog
        
        @tool
        async def read_user_memory(user_id: int) -> str:
            """Reads the personal memory or preferences stored for a specific user.
    
            Use this tool when you need to know if the user has previously asked
            you to remember something (e.g., their name, a specific interaction
            style, or other preferences).
    
            Args:
                user_id: The Discord user's ID.
    
            Returns:
                A string containing the stored memory. If no memory is found,
                it returns a "not found" message. If the requested user is not in
                the DB, fallback to the message author when available.
            """
            cog = get_cog()
            if not cog:
                return "Error: Personal memory system (UserDataCog) is not loaded."
    
            try:
                logger.info(
                    "Reading personal memory",
                    extra={"user_id": user_id}
                )
    
                # Determine effective user id. If the LLM provided an invalid value,
                # default to the author of the triggering message (if available).
                effective_id = None
                try:
                    # Accept ints and int-like strings
                    effective_id = int(user_id)
                except Exception:
                    msg = getattr(runtime, "message", None)
                    if msg and getattr(msg, "author", None):
                        logger.warning(
                            "read_user_memory: LLM provided invalid user_id; defaulting to message author",
                            extra={"provided_user_id": user_id, "author_id": getattr(msg.author, "id", None)}
                        )
                        effective_id = msg.author.id
                    else:
                        # No message context: fall back to string form of provided id.
                        logger.warning(
                            "read_user_memory: invalid user_id and no message context; using raw value",
                            extra={"user_id": user_id}
                        )
                        effective_id = user_id
    
                # If the provided id exists in DB use it; otherwise fallback to message author (if available).
                try:
                    user_mgr = getattr(cog, "user_manager", None)
                    if user_mgr:
                        exists = await user_mgr.get_user_info(str(effective_id))
                        if not exists:
                            msg = getattr(runtime, "message", None)
                            author_id = None
                            if msg and getattr(msg, "author", None):
                                author_id = getattr(msg.author, "id", None)
                            # If no author found, try interaction user on runtime.message if it's an Interaction
                            if not author_id:
                                maybe_interaction = getattr(runtime, "message", None)
                                if isinstance(maybe_interaction, discord.Interaction) and getattr(maybe_interaction, "user", None):
                                    author_id = getattr(maybe_interaction.user, "id", None)
                            if author_id:
                                logger.info(
                                    "Requested user not in DB; falling back to message author",
                                    extra={"requested_user_id": effective_id, "author_id": author_id}
                                )
                                effective_id = author_id
                except Exception as e:
                    logger.warning(f"read_user_memory: fallback existence check failed: {e}")
    
                # Ensure cog receives a string user_id (storage uses text keys).
                return await cog._read_user_data(
                    str(effective_id),
                    cast(
                        Union[discord.Interaction, discord.Message],
                        getattr(runtime, "message", None)
                    ),
                )
            except Exception as e:
                await func.report_error(
                    e, f"Failed to read personal memory for user_id={user_id}"
                )
                return f"An unexpected error occurred while reading memory: {e}"

        @tool
        async def save_user_memory(user_id: int, memory_to_save: str) -> str:
            """Saves or updates a personal memory or preference for a specific user.
    
            Use this tool only when the user **explicitly asks** you to remember
            something (e.g., "My name is Bob," "Please call me Master,"
            "I am a Python developer"). This new information will be intelligently
            merged with any existing memory.
    
            Args:
                user_id: The Discord user's ID.
                memory_to_save: The new piece of information to remember.
    
            Returns:
                A string confirming that the memory was successfully saved or updated,
                or an error message if the operation failed.
            """
            cog = get_cog()
            if not cog:
                return "Error: Personal memory system (UserDataCog) is not loaded."
            
            if not memory_to_save or memory_to_save.strip() == "":
                return "Error: 'memory_to_save' parameter cannot be empty."
    
            try:
                logger.info(
                    "Saving personal memory",
                    extra={"user_id": user_id}
                )
    
                # Determine effective user id. If the LLM provided an invalid value,
                # default to the author of the triggering message (if available).
                effective_id = None
                try:
                    effective_id = int(user_id)
                except Exception:
                    msg = getattr(runtime, "message", None)
                    if msg and getattr(msg, "author", None):
                        logger.warning(
                            "save_user_memory: LLM provided invalid user_id; defaulting to message author",
                            extra={"provided_user_id": user_id, "author_id": getattr(msg.author, "id", None)}
                        )
                        effective_id = msg.author.id
                    else:
                        logger.warning(
                            "save_user_memory: invalid user_id and no message context; using raw value",
                            extra={"user_id": user_id}
                        )
                        effective_id = user_id
    
                # Get the display_name for storage. Prefer cache (get_user) and fall back to fetch_user.
                bot = get_bot()
                display_name = f"User_{effective_id}"
                if bot:
                    try:
                        fetched_user = None
                        # try convert to integer id when possible
                        try:
                            int_id = int(effective_id)
                        except Exception:
                            int_id = None
                        if int_id is not None:
                            # prefer cache to avoid unnecessary API calls
                            fetched_user = bot.get_user(int_id)
                            if not fetched_user:
                                try:
                                    fetched_user = await bot.fetch_user(int_id)
                                except discord.NotFound:
                                    # user does not exist / was deleted - not an exception to escalate
                                    logger.warning(
                                        f"fetch_user: unknown user {int_id}",
                                        extra={"provided_user_id": user_id}
                                    )
                                    fetched_user = None

                                    # Fallback to message author if the provided ID is invalid/unknown
                                    # This handles cases where LLM hallucinates an ID (e.g. Guild ID)
                                    msg = getattr(runtime, "message", None)
                                    if msg and getattr(msg, "author", None):
                                        author_id = getattr(msg.author, "id", None)
                                        if author_id and author_id != int_id:
                                            logger.info(
                                                f"Falling back to message author {author_id} after invalid user_id {int_id}",
                                                extra={"original_id": int_id, "new_id": author_id}
                                            )
                                            effective_id = author_id
                                            fetched_user = msg.author

                                except discord.HTTPException as he:
                                    # transient HTTP error - report and continue with fallback
                                    logger.warning(
                                        f"fetch_user HTTP error for {int_id}: {he}",
                                        extra={"provided_user_id": user_id}
                                    )
                                    await func.report_error(he, f"Failed to fetch user {int_id}")
                                except Exception as e:
                                    # unexpected error - log and report
                                    logger.exception(
                                        f"Unexpected error fetching user {int_id}: {e}"
                                    )
                                    await func.report_error(e, f"Failed to fetch user {int_id}")
                        # If we obtained a user object, prefer its display_name/name
                        if fetched_user:
                            display_name = getattr(
                                fetched_user,
                                "display_name",
                                getattr(fetched_user, "name", display_name)
                            )
                    except Exception as fetch_err:
                        # Ensure any unexpected outer errors are at least warned; report for observability.
                        logger.warning(
                            f"Failed to fetch display_name for user {effective_id}: {fetch_err}",
                            extra={"provided_user_id": user_id}
                        )
                        try:
                            await func.report_error(fetch_err, f"Failed to fetch display_name for user {effective_id}")
                        except Exception:
                            pass
    
                # Debug details about what will be saved
                logger.debug(
                    "save_user_memory inputs",
                    extra={"user_id": effective_id, "display_name": display_name, "memory_length": len(memory_to_save)}
                )
    
                # Call the internal method from UserDataCog with correct parameter order:
                # (user_id: str, display_name: str, user_data: str, context)
                return await cog._save_user_data(
                    str(effective_id),
                    display_name,
                    memory_to_save,
                    cast(
                        Union[discord.Interaction, discord.Message],
                        getattr(runtime, "message", None)
                    ),
                )
            except Exception as e:
                await func.report_error(
                    e, f"Failed to save personal memory for user_id={user_id}"
                )
                return f"An unexpected error occurred while saving memory: {e}"

        return [read_user_memory, save_user_memory]
