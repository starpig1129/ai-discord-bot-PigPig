from typing import List, Dict

from llm.memory.schema import ProceduralMemory, UserInfo
from cogs.memory.users.manager import SQLiteUserManager
from function import func


class ProceduralMemoryProvider:
    """Provides procedural memory for multiple users.

    The provider fetches UserInfo for each user_id using the provided user manager
    and returns a ProceduralMemory mapping user_id -> UserInfo.
    """

    def __init__(self, user_manager: SQLiteUserManager):
        """Initializes the provider with a user manager instance."""
        self.user_manager = user_manager

    async def get(self, user_ids: List[str]) -> ProceduralMemory:
        """Fetch procedural memory for a list of user IDs.

        Args:
            user_ids: List of user id strings to fetch info for.

        Returns:
            ProceduralMemory containing a dict mapping user_id to UserInfo.
        """
        if not user_ids:
            return ProceduralMemory(user_info={})

        try:
            # Use user_manager's batch method which already reports per-user errors.
            users: Dict[str, UserInfo] = await self.user_manager.get_multiple_users(
                [str(uid) for uid in user_ids]
            )
        except Exception as e:
            # Report and return empty mapping to keep flow resilient.
            await func.report_error(e, "ProceduralMemoryProvider.get failed while fetching users")
            users = {}

        return ProceduralMemory(user_info=users)