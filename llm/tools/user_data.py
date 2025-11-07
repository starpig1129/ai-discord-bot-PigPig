# MIT License
# Copyright (c) 2024 starpig1129

import logging
import discord
from typing import Optional, Any, TYPE_CHECKING, Union, cast
 
from langchain.tools import tool
from function import func
from cogs.userdata import UserDataCog
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

class UserMemoryTools:
    """
    Provides tools for a LangChain Agent to manage a user's "personal memory" 
    (also known as procedural memory).

    This toolset encapsulates the UserDataCog's functionality, allowing the Agent 
    to read or save specific preferences, facts, or interaction rules that 
    the user has previously asked the bot to remember.
    """

    def __init__(self, runtime: "OrchestratorRequest"):
        """
        Initializes the tool's runtime environment.
    
        Args:
            runtime: Which contains the context
                     (bot, logger, etc.).
        """
        self.runtime = runtime
        self.logger = getattr(self.runtime, "logger", logging.getLogger(__name__))

    def _get_bot(self) -> Optional[Any]:
        """Safely retrieves the bot instance from the runtime."""
        bot = getattr(self.runtime, "bot", None)
        if not bot:
            self.logger.error("Bot instance not available in runtime.")
        return bot

    def _get_cog(self) -> Optional[UserDataCog]:
        """Safely retrieves the UserDataCog."""
        bot = self._get_bot()
        if not bot:
            return None
        
        cog = bot.get_cog("UserDataCog")
        if not cog:
            self.logger.error("UserDataCog is not loaded.")
            return None
    
        
        return cog

    @tool
    async def read_user_memory(self, user_id: int) -> str:
        """
        Reads the "personal memory" or "preferences" stored for a specific user.

        Use this tool when you need to know if the user has previously asked you to remember
        something (e.g., their name, a specific interaction style, or other preferences).

        Args:
            user_id: The Discord user's ID.

        Returns:
            A string containing the stored memory. If no memory is found, 
            it returns a "not found" message.
        """
        cog = self._get_cog()
        if not cog:
            return "Error: Personal memory system (UserDataCog) is not loaded."

        try:
            self.logger.info(f"Reading personal memory for user_id={user_id}")
            # Call the internal method from UserDataCog
            return await cog._read_user_data(
                str(user_id),
                cast(Union[discord.Interaction, discord.Message], getattr(self.runtime, "message", None)),
            )
        except Exception as e:
            await func.report_error(
                e, f"Failed to read personal memory for user_id={user_id}"
            )
            return f"An unexpected error occurred while reading memory: {e}"

    @tool
    async def save_user_memory(self, user_id: int, memory_to_save: str) -> str:
        """
        Saves or updates a "personal memory" or "preference" for a specific user.

        Use this tool only when the user **explicitly asks** you to remember something 
        (e.g., "My name is Bob," "Please call me Master," "I am a Python developer").
        This new information will be intelligently merged with any existing memory.

        Args:
            user_id: The Discord user's ID.
            memory_to_save: The new piece of information to remember.

        Returns:
            A string confirming that the memory was successfully saved or updated.
        """
        cog = self._get_cog()
        if not cog:
            return "Error: Personal memory system (UserDataCog) is not loaded."
        
        if not memory_to_save or memory_to_save.strip() == "":
             return "Error: 'memory_to_save' parameter cannot be empty."

        try:
            self.logger.info(f"Saving personal memory for user_id={user_id}")
            
            # Get the display_name for storage
            bot = self._get_bot()
            display_name = f"User_{user_id}"
            if bot:
                try:
                    user = await bot.fetch_user(user_id)
                    # discord.User has .display_name in certain contexts; fallback to name/nick
                    display_name = getattr(user, "display_name", getattr(user, "name", display_name))
                except Exception as fetch_err:
                    self.logger.warning(f"Failed to fetch display_name for user {user_id}: {fetch_err}")

            # Call the internal method from UserDataCog
            return await cog._save_user_data(
                str(user_id),
                display_name,
                memory_to_save,
                cast(Union[discord.Interaction, discord.Message], getattr(self.runtime, "message", None)),
            )
        except Exception as e:
            await func.report_error(
                e, f"Failed to save personal memory for user_id={user_id}"
            )
            return f"An unexpected error occurred while saving memory: {e}"