import discord
from llm.memory.schema import ProceduralMemory
from cogs.memory.users.manager import SQLiteUserManager


class ProceduralMemoryProvider:
    """Provides procedural memory by fetching user-specific background
    and preferences from the user manager.
    """

    def __init__(self, user_manager: SQLiteUserManager):
        """Initializes the provider with a user manager instance.

        Args:
            user_manager (SQLiteUserManager): An instance of the user manager
                                              that handles database operations.
        """
        self.user_manager = user_manager

    async def get(self, message: discord.Message) -> ProceduralMemory:
        """Fetches the user's background information.

        Args:
            message (discord.Message): The current message object.

        Returns:
            ProceduralMemory: An object containing the user's info.
        """
        user_id = str(message.author.id)
        user_info = await self.user_manager.get_user_info(user_id)
        return ProceduralMemory(user_info=user_info)