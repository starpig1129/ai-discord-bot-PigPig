"""User manager depending on StorageInterface."""
import logging
import asyncio
import json
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

from cogs.memory.interfaces.storage_interface import StorageInterface
from cogs.memory.users.models import UserInfo
from function import func

logger = logging.getLogger(__name__)


class SQLiteUserManager:
    """Lightweight user manager that delegates storage operations to StorageInterface.

    Responsibilities:
    - delegate persistence to provided storage
    - in-memory caching and business logic
    """

    def __init__(self, storage: StorageInterface):
        """Initialize with a StorageInterface implementation."""
        self.storage = storage
        self.logger = logger
        self._user_cache: Dict[str, UserInfo] = {}
        self._cache_size_limit = 1000

    async def get_user_info(self, user_id: str, use_cache: bool = True) -> Optional[UserInfo]:
        """Retrieve user info via storage and update cache."""
        if use_cache and user_id in self._user_cache:
            return self._user_cache[user_id]
        try:
            user_info = await self.storage.get_user_info(user_id)
            if user_info and use_cache:
                self._update_cache(user_id, user_info)
            return user_info
        except Exception as e:
            await func.report_error(e, f"Failed to retrieve user info (user: {user_id})")
            return None

    async def get_multiple_users(self, user_ids: List[str], use_cache: bool = True) -> Dict[str, UserInfo]:
        """Retrieve multiple users, leveraging cache and storage concurrently."""
        result: Dict[str, UserInfo] = {}
        uncached: List[str] = []
        if use_cache:
            for uid in user_ids:
                if uid in self._user_cache:
                    result[uid] = self._user_cache[uid]
                else:
                    uncached.append(uid)
        else:
            uncached = user_ids[:]

        if uncached:
            try:
                coros = [self.storage.get_user_info(uid) for uid in uncached]
                rows = await asyncio.gather(*coros, return_exceptions=True)
                for uid, row in zip(uncached, rows):
                    if isinstance(row, Exception):
                        await func.report_error(row, f"get_user_info failed for {uid}")
                        continue
                    if isinstance(row, UserInfo):
                        result[uid] = row
                        if use_cache:
                            self._update_cache(uid, row)
            except Exception as e:
                await func.report_error(e, "Failed to retrieve multiple users")
        return result

    async def update_user_data(self, user_id: str, user_data: Any, display_name: Optional[str] = None) -> bool:
        """Extracts fields from user_data and delegates to storage."""
        try:
            # user_data is expected to be a UserDataResponse object
            procedural_memory = user_data.procedural_memory
            user_background = user_data.user_background
            display_names = user_data.display_names

            # Ensure display_name from context is included
            if display_name and display_name not in display_names:
                display_names.append(display_name)

            success = await self.storage.update_user_data(
                discord_id=user_id,
                discord_name=display_name or "",
                procedural_memory=procedural_memory,
                user_background=user_background,
                display_names=display_names
            )

            if success and user_id in self._user_cache:
                del self._user_cache[user_id]
            return success
        except Exception as e:
            await func.report_error(e, f"Failed to update user data (user: {user_id})")
            return False

    async def update_user_activity(self, user_id: str, display_name: str = "") -> bool:
        """Delegate activity update to storage and invalidate cache."""
        try:
            success = await self.storage.update_user_activity(user_id, display_name)
            if success and user_id in self._user_cache:
                del self._user_cache[user_id]
            return success
        except Exception as e:
            await func.report_error(e, f"Failed to update user activity (user: {user_id})")
            return False

    async def search_users_by_display_name(self, name_pattern: str, limit: int = 10) -> List[UserInfo]:
        """Attempt to use storage search; fall back to simple cache scan if unavailable.
 
        Fallback checks both `discord_name` and entries in `display_names`.
        """
        try:
            if hasattr(self.storage, "search_users_by_display_name"):
                return await getattr(self.storage, "search_users_by_display_name")(name_pattern, limit)
            # fallback: scan cache for matches
            results: List[UserInfo] = []
            pattern = name_pattern.lower()
            for ui in self._user_cache.values():
                candidate_names = []
                if getattr(ui, "discord_name", None):
                    candidate_names.append(ui.discord_name)
                if getattr(ui, "display_names", None):
                    candidate_names.extend(ui.display_names)
                for n in candidate_names:
                    if n and pattern in n.lower():
                        results.append(ui)
                        break
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            await func.report_error(e, f"Failed to search users (pattern: {name_pattern})")
            return []

    async def get_user_statistics(self) -> Dict[str, Any]:
        """Return statistics; delegate to storage if available otherwise return cache-based stats."""
        try:
            if hasattr(self.storage, "get_user_statistics"):
                return await getattr(self.storage, "get_user_statistics")()
            return {"total_users": 0, "users_with_data": 0, "active_users_7d": 0, "active_users_30d": 0,
                    "cache_size": len(self._user_cache)}
        except Exception as e:
            await func.report_error(e, "Failed to retrieve user statistics")
            return {"cache_size": len(self._user_cache)}

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
                        ok = await self.update_user_data(user_id, user_data, display)
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

    def _update_cache(self, user_id: str, user_info: UserInfo):
        """Update in-memory cache with eviction."""
        try:
            if len(self._user_cache) >= self._cache_size_limit:
                oldest = next(iter(self._user_cache))
                del self._user_cache[oldest]
            self._user_cache[user_id] = user_info
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Failed to update user cache"))

    def clear_cache(self):
        """Clear in-memory cache."""
        self._user_cache.clear()
        self.logger.info("User cache cleared")

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