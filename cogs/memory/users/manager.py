"""User manager depending on StorageInterface."""
import logging
import asyncio
from typing import Dict, List, Optional, Any

from cogs.memory.interfaces.storage_interface import StorageInterface
from cogs.memory.users.models import UserInfo
from function import func

logger = logging.getLogger(__name__)


class SQLiteUserManager:
    """Lightweight user manager that delegates storage operations to StorageInterface.

    Responsibilities:
    - delegate persistence to provided storage
    - coordinate user data operations
    """

    def __init__(self, storage: StorageInterface):
        """Initialize with a StorageInterface implementation."""
        self.storage = storage
        self.logger = logger

    async def get_user_info(self, user_id: str, use_cache: bool = True) -> Optional[UserInfo]:
        """Retrieve user info via storage (storage handles its own caching)."""
        try:
            return await self.storage.get_user_info(user_id)
        except Exception as e:
            await func.report_error(e, f"Failed to retrieve user info (user: {user_id})")
            return None

    async def get_multiple_users(self, user_ids: List[str], use_cache: bool = True) -> Dict[str, UserInfo]:
        """Retrieve multiple users concurrently (storage handles caching)."""
        result: Dict[str, UserInfo] = {}
        try:
            if hasattr(self.storage, "get_users_info"):
                # Use batched optimized method if available (avoids N+1 queries)
                batch_results = await getattr(self.storage, "get_users_info")(user_ids)
                for uid, info in batch_results.items():
                    result[uid] = info
            else:
                # Fallback to concurrent gather approach
                coros = [self.storage.get_user_info(uid) for uid in user_ids]
                rows = await asyncio.gather(*coros, return_exceptions=True)
                for uid, row in zip(user_ids, rows):
                    if isinstance(row, Exception):
                        await func.report_error(row, f"get_user_info failed for {uid}")
                        continue
                    if isinstance(row, UserInfo):
                        result[uid] = row
        except Exception as e:
            await func.report_error(e, "Failed to retrieve multiple users")
        return result

    async def update_user_data(self, user_id: str, user_data: Any, discord_name: Optional[str] = None, nickname: Optional[str] = None) -> bool:
        """Extracts fields from user_data and delegates to storage."""
        try:
            # user_data is expected to be a UserDataResponse object
            procedural_memory = user_data.procedural_memory
            user_background = user_data.user_background
            display_names = user_data.display_names

            # Ensure nickname from context is included
            if nickname and nickname not in display_names:
                display_names.append(nickname)
            # Ensure discord_name from context is included
            if discord_name and discord_name not in display_names:
                display_names.append(discord_name)

            return await self.storage.update_user_data(
                discord_id=user_id,
                discord_name=discord_name or "",
                procedural_memory=procedural_memory,
                user_background=user_background,
                display_names=display_names,
                nickname=nickname
            )
        except Exception as e:
            await func.report_error(e, f"Failed to update user data (user: {user_id})")
            return False

    async def delete_user_data(self, user_id: str) -> bool:
        """Delegate deletion to storage."""
        try:
            return await self.storage.delete_user_data(user_id)
        except Exception as e:
            await func.report_error(e, f"Failed to delete user data (user: {user_id})")
            return False

    async def update_user_activity(self, user_id: str, discord_name: str = "", nickname: Optional[str] = None) -> bool:
        """Delegate activity update to storage."""
        try:
            return await self.storage.update_user_activity(user_id, discord_name, nickname)
        except Exception as e:
            await func.report_error(e, f"Failed to update user activity (user: {user_id})")
            return False

    async def search_users_by_display_name(self, name_pattern: str, limit: int = 10) -> List[UserInfo]:
        """Search users by display name via storage."""
        try:
            if hasattr(self.storage, "search_users_by_display_name"):
                return await getattr(self.storage, "search_users_by_display_name")(name_pattern, limit)
            return []
        except Exception as e:
            await func.report_error(e, f"Failed to search users (pattern: {name_pattern})")
            return []

    async def get_all_users(self, limit: int = 500, offset: int = 0) -> List[UserInfo]:
        """Return all users from storage; delegates to storage.get_all_users if available."""
        try:
            if hasattr(self.storage, "get_all_users"):
                return await self.storage.get_all_users(limit=limit, offset=offset)
            return []
        except Exception as e:
            await func.report_error(e, "SQLiteUserManager.get_all_users failed")
            return []

    async def get_users_count(self) -> int:
        """Return total user count from storage."""
        try:
            if hasattr(self.storage, "get_users_count"):
                return await self.storage.get_users_count()
            return 0
        except Exception as e:
            await func.report_error(e, "SQLiteUserManager.get_users_count failed")
            return 0

    async def get_user_statistics(self) -> Dict[str, Any]:
        """Return statistics from storage."""
        try:
            if hasattr(self.storage, "get_user_statistics"):
                return await getattr(self.storage, "get_user_statistics")()
            return {"total_users": 0, "users_with_data": 0, "active_users_7d": 0, "active_users_30d": 0}
        except Exception as e:
            await func.report_error(e, "Failed to retrieve user statistics")
            return {}

    async def migrate_from_mongodb(self, mongodb_collection) -> int:
        """Migrate users by delegating to update_user_data for each document."""
        try:
            self.logger.info("Starting migration of users from MongoDB...")
            mongodb_users = list(mongodb_collection.find({}))
            migrated = 0
            failed = 0
            for doc in mongodb_users:
                try:
                    user_id = doc.get("user_id")
                    user_data = doc.get("user_data")
                    display = doc.get("display_name") or ""
                    if user_id and user_data:
                        ok = await self.update_user_data(user_id, user_data, discord_name=display)
                        if ok:
                            migrated += 1
                        else:
                            failed += 1
                    else:
                        self.logger.warning("Skipping invalid user document: %s", doc.get("_id"))
                        failed += 1
                except Exception as e:
                    await func.report_error(e, f"MongoDB user migration failed (ID: {doc.get('_id')})")
                    failed += 1
            self.logger.info("MongoDB migration completed: %d succeeded, %d failed, total %d", migrated, failed, len(mongodb_users))
            return migrated
        except Exception as e:
            await func.report_error(e, "MongoDB user migration failed")
            return 0


    async def cleanup_inactive_users(self, days: int = 365) -> int:
        """Delegate cleanup if storage provides method; otherwise no-op."""
        try:
            if hasattr(self.storage, "cleanup_inactive_users"):
                return await getattr(self.storage, "cleanup_inactive_users")(days)
            return 0
        except Exception as e:
            await func.report_error(e, "Failed to cleanup inactive users")
            return 0


def extract_participant_ids(message, conversation_history: List[Any]) -> set:
    """Extract participant IDs from a message and recent conversation history.

    Args:
        message: Discord message object
        conversation_history: list of recent messages or dicts representing messages

    Returns:
        set: set of participant ID strings
    """
    participant_ids = set()

    if hasattr(message, "author") and getattr(message.author, "id", None) is not None:
        participant_ids.add(str(message.author.id))

    if hasattr(message, "mentions"):
        for mention in message.mentions:
            mention_id = getattr(mention, "id", None)
            if mention_id is None:
                try:
                    mention_id = mention
                except Exception:
                    continue
            participant_ids.add(str(mention_id))

    for msg in conversation_history[-10:]:
        if isinstance(msg, dict):
            if "user_id" in msg and msg["user_id"] is not None:
                participant_ids.add(str(msg["user_id"]))
            elif "author" in msg and hasattr(msg["author"], "id"):
                participant_ids.add(str(msg["author"].id))
        else:
            if hasattr(msg, "author") and getattr(msg.author, "id", None) is not None:
                participant_ids.add(str(msg.author.id))

    return participant_ids
