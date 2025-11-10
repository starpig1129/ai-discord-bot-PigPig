"""SQLite user manager moved from cogs/memory/user_manager.py.

Contains SQLiteUserManager and helper functions.
"""
import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any
import asyncio

from .models import UserInfo
from ..exceptions import DatabaseError
from function import func


class SQLiteUserManager:
    """SQLite user manager.
 
    Manages Discord user information, profiles and preferences.
    Supports migration from MongoDB and bulk queries.
    """

    def __init__(self, db_manager):
        """Initialize user manager

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        self._user_cache = {}  # Simple in-memory cache
        self._cache_size_limit = 1000  # Cache size limit

        self._ensure_user_tables()

    def _ensure_user_tables(self):
        """Ensure user-related tables exist in the database."""
        try:
            with self.db_manager.get_connection() as conn:
                # Create users table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        discord_id TEXT,
                        display_name TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                        user_data TEXT,
                        preferences TEXT
                    )
                """)

                # Create user_profiles table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        profile_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        profile_data TEXT,
                        interaction_history TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id)
                            ON DELETE CASCADE
                    )
                """)

                # Create indexes
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_users_user_id
                    ON users(user_id)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_users_discord_id ON users(discord_id)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_users_last_active
                    ON users(last_active)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id 
                    ON user_profiles(user_id)
                """)

                conn.commit()
                self.logger.info("User tables initialized")
 
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Failed to create user tables"))
            raise DatabaseError(f"Failed to create user tables: {e}")

    async def get_user_info(self, user_id: str, use_cache: bool = True) -> Optional[UserInfo]:
        """Retrieve full user information.
 
        Args:
            user_id: The user identifier.
            use_cache: Whether to use in-memory cache.
 
        Returns:
            UserInfo instance or None if not found.
        """
        # Check cache
        if use_cache and user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT u.user_id, u.display_name, u.user_data,
                           u.last_active, u.preferences, u.created_at, up.profile_data
                    FROM users u
                    LEFT JOIN user_profiles up ON u.user_id = up.user_id
                    WHERE u.user_id = ?
                """, (user_id,))

                row = cursor.fetchone()
                if row:
                    # Parse JSON data
                    preferences = None
                    if row[4]:
                        try:
                            preferences = json.loads(row[4])
                        except json.JSONDecodeError:
                            self.logger.warning(f"Unable to parse preferences for user {user_id}")

                    profile_data = None
                    if row[6]:
                        try:
                            profile_data = json.loads(row[6])
                        except json.JSONDecodeError:
                            self.logger.warning(f"Unable to parse profile data for user {user_id}")

                    # Handle datetime fields
                    last_active = None
                    if row[3]:
                        try:
                            last_active = datetime.fromisoformat(row[3])
                        except (ValueError, TypeError):
                            pass

                    created_at = None
                    if row[5]:
                        try:
                            created_at = datetime.fromisoformat(row[5])
                        except (ValueError, TypeError):
                            pass

                    user_info = UserInfo(
                        user_id=row[0],
                        display_name=row[1] or "",
                        user_data=row[2],
                        last_active=last_active,
                        preferences=preferences,
                        created_at=created_at,
                        profile_data=profile_data
                    )

                    # Update cache
                    if use_cache:
                        self._update_cache(user_id, user_info)

                    return user_info

                return None

        except Exception as e:
            await func.report_error(e, f"Failed to retrieve user info (user: {user_id})")
            return None

    async def get_multiple_users(self, user_ids: List[str], use_cache: bool = True) -> Dict[str, UserInfo]:
        """Retrieve multiple users in a single query.
 
        Args:
            user_ids: List of user identifiers.
            use_cache: Whether to consult the in-memory cache first.
 
        Returns:
            Dict mapping user_id to UserInfo for found users.
        """
        result = {}
        uncached_ids = []

        # Check cache
        if use_cache:
            for user_id in user_ids:
                if user_id in self._user_cache:
                    result[user_id] = self._user_cache[user_id]
                else:
                    uncached_ids.append(user_id)
        else:
            uncached_ids = user_ids

        # Query uncached users
        if uncached_ids:
            try:
                placeholders = ','.join('?' for _ in uncached_ids)
                with self.db_manager.get_connection() as conn:
                    cursor = conn.execute(f"""
                        SELECT u.user_id, u.display_name, u.user_data,
                               u.last_active, u.preferences, u.created_at, up.profile_data
                        FROM users u
                        LEFT JOIN user_profiles up ON u.user_id = up.user_id
                        WHERE u.user_id IN ({placeholders})
                    """, uncached_ids)

                    for row in cursor.fetchall():
                        # Parse data (same logic as get_user_info)
                        preferences = None
                        if row[4]:
                            try:
                                preferences = json.loads(row[4])
                            except json.JSONDecodeError:
                                pass

                        profile_data = None
                        if row[6]:
                            try:
                                profile_data = json.loads(row[6])
                            except json.JSONDecodeError:
                                pass

                        last_active = None
                        if row[3]:
                            try:
                                last_active = datetime.fromisoformat(row[3])
                            except (ValueError, TypeError):
                                pass

                        created_at = None
                        if row[5]:
                            try:
                                created_at = datetime.fromisoformat(row[5])
                            except (ValueError, TypeError):
                                pass

                        user_info = UserInfo(
                            user_id=row[0],
                            display_name=row[1] or "",
                            user_data=row[2],
                            last_active=last_active,
                            preferences=preferences,
                            created_at=created_at,
                            profile_data=profile_data
                        )

                        result[row[0]] = user_info

                        # Update cache
                        if use_cache:
                            self._update_cache(row[0], user_info)

            except Exception as e:
                await func.report_error(e, "Failed to retrieve multiple users")

        return result

    async def update_user_data(self, user_id: str, user_data: str,
                               display_name: Optional[str] = None,
                               preferences: Optional[Dict] = None) -> bool:
        """Create or update user's stored data and preferences.
 
        Args:
            user_id: The user identifier.
            user_data: Arbitrary user data (stored as text).
            display_name: Optional display name to set or update.
            preferences: Optional preferences dict to store as JSON.
 
        Returns:
            True on success, False on failure.
        """
        try:
            logging.debug(f"update_user_data called with user_id={user_id}, display_name={display_name}, preferences={preferences}")
            with self.db_manager.get_connection() as conn:
                # Check if user exists
                cursor = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                exists = cursor.fetchone()

                preferences_json = json.dumps(preferences, ensure_ascii=False) if preferences else None

                try:
                    # Sync discord_id field (for compatibility with existing database schema)
                    discord_id_val = user_id

                    if exists:
                        # Update existing user, ensure discord_id is also updated or maintained
                        conn.execute("""
                            UPDATE users
                            SET user_data = ?,
                                display_name = COALESCE(?, display_name),
                                preferences = COALESCE(?, preferences),
                                discord_id = COALESCE(?, discord_id),
                                last_active = CURRENT_TIMESTAMP
                            WHERE user_id = ?
                        """, (user_data, display_name, preferences_json, discord_id_val, user_id))
                    else:
                        # Create new user, include discord_id field to avoid NOT NULL constraint
                        conn.execute("""
                            INSERT INTO users (user_id, discord_id, display_name, user_data, preferences)
                            VALUES (?, ?, ?, ?, ?)
                        """, (user_id, discord_id_val, display_name, user_data, preferences_json))

                    conn.commit()
                except sqlite3.IntegrityError as ie:
                    # On integrity error, capture schema to help diagnosis and report
                    try:
                        schema_rows = conn.execute("PRAGMA table_info('users')").fetchall()
                    except Exception as schema_exc:
                        schema_rows = f"failed to get schema: {schema_exc}"
                    logging.error(f"IntegrityError updating user {user_id}: {ie}; users schema: {schema_rows}")
                    await func.report_error(ie, f"Failed to update user data (user: {user_id}); schema: {schema_rows}")
                    return False

                # Invalidate cache for this user
                if user_id in self._user_cache:
                    del self._user_cache[user_id]
 
                self.logger.info(f"User data updated: {user_id}")
                return True
 
        except Exception as e:
            await func.report_error(e, f"Failed to update user data (user: {user_id})")
            return False

    async def update_user_activity(self, user_id: str, display_name: str = '') -> bool:
        """Update user activity timestamp

        Args:
            user_id: User ID
            display_name: Display name (optional)

        Returns:
            bool: Whether update was successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                # Ensure user record exists
                cursor = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                exists = cursor.fetchone()

                if exists:
                    # Update activity timestamp
                    conn.execute("""
                        UPDATE users 
                        SET last_active = CURRENT_TIMESTAMP,
                            display_name = COALESCE(?, display_name)
                        WHERE user_id = ?
                    """, (display_name, user_id))
                else:
                    # Create new user record (include discord_id to satisfy existing schema's NOT NULL constraint)
                    conn.execute("""
                        INSERT INTO users (user_id, discord_id, display_name)
                        VALUES (?, ?, ?)
                    """, (user_id, user_id, display_name))

                conn.commit()

                # Clear cache
                if user_id in self._user_cache:
                    del self._user_cache[user_id]

                return True

        except Exception as e:
            await func.report_error(e, f"Failed to update user activity (user: {user_id})")
            return False

    async def search_users_by_display_name(self, name_pattern: str, limit: int = 10) -> List[UserInfo]:
        """Search users by display name using SQL LIKE.
 
        Args:
            name_pattern: Pattern to match against display_name.
            limit: Maximum number of results.
 
        Returns:
            List of UserInfo objects matching the pattern.
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT u.user_id, u.display_name, u.user_data,
                           u.last_active, u.preferences, u.created_at, up.profile_data
                    FROM users u
                    LEFT JOIN user_profiles up ON u.user_id = up.user_id
                    WHERE u.display_name LIKE ?
                    ORDER BY u.last_active DESC
                    LIMIT ?
                """, (f"%{name_pattern}%", limit))

                results = []
                for row in cursor.fetchall():
                    # Parse data (same logic as get_user_info)
                    preferences = None
                    if row[4]:
                        try:
                            preferences = json.loads(row[4])
                        except json.JSONDecodeError:
                            pass

                    profile_data = None
                    if row[6]:
                        try:
                            profile_data = json.loads(row[6])
                        except json.JSONDecodeError:
                            pass

                    last_active = None
                    if row[3]:
                        try:
                            last_active = datetime.fromisoformat(row[3])
                        except (ValueError, TypeError):
                            pass

                    created_at = None
                    if row[5]:
                        try:
                            created_at = datetime.fromisoformat(row[5])
                        except (ValueError, TypeError):
                            pass

                    user_info = UserInfo(
                        user_id=row[0],
                        display_name=row[1] or "",
                        user_data=row[2],
                        last_active=last_active,
                        preferences=preferences,
                        created_at=created_at,
                        profile_data=profile_data
                    )
                    results.append(user_info)

                return results

        except Exception as e:
            await func.report_error(e, f"Failed to search users (pattern: {name_pattern})")
            return []

    async def get_user_statistics(self) -> Dict[str, Any]:
        """Get aggregated user statistics from the database.
 
        Returns:
            Dictionary with total_users, users_with_data, active_users_7d, active_users_30d and cache_size.
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_users,
                        COUNT(CASE WHEN user_data IS NOT NULL THEN 1 END) as users_with_data,
                        COUNT(CASE WHEN last_active > datetime('now', '-7 days') THEN 1 END) as active_users_7d,
                        COUNT(CASE WHEN last_active > datetime('now', '-30 days') THEN 1 END) as active_users_30d
                    FROM users
                """)

                row = cursor.fetchone()
                return {
                    "total_users": row[0],
                    "users_with_data": row[1],
                    "active_users_7d": row[2],
                    "active_users_30d": row[3],
                    "cache_size": len(self._user_cache)
                }

        except Exception as e:
            await func.report_error(e, "Failed to retrieve user statistics")
            return {}

    async def migrate_from_mongodb(self, mongodb_collection) -> int:
        """Migrate user documents from a MongoDB collection into SQLite.
 
        Args:
            mongodb_collection: A pymongo Collection-like object.
 
        Returns:
            Number of users successfully migrated.
        """
        try:
            self.logger.info("Starting migration of users from MongoDB...")
 
            # load all MongoDB documents
            mongodb_users = list(mongodb_collection.find({}))
            total_users = len(mongodb_users)
 
            if total_users == 0:
                self.logger.info("No users to migrate from MongoDB")
                return 0

            migrated_count = 0
            failed_count = 0

            for user_doc in mongodb_users:
                try:
                    user_id = user_doc.get('user_id')
                    user_data = user_doc.get('user_data')

                    if user_id and user_data:
                        success = await self.update_user_data(user_id, user_data)
                        if success:
                            migrated_count += 1
                        else:
                            failed_count += 1
                    else:
                        self.logger.warning(f"Skipping invalid user document: {user_doc.get('_id')}")
                        failed_count += 1

                except Exception as e:
                    await func.report_error(e, f"MongoDB user migration failed (ID: {user_doc.get('_id')})")
                    failed_count += 1

            self.logger.info(f"MongoDB migration completed: {migrated_count} succeeded, {failed_count} failed, total {total_users}")
            return migrated_count

        except Exception as e:
            await func.report_error(e, "MongoDB user migration failed")
            return 0

    def _update_cache(self, user_id: str, user_info: UserInfo):
        """Update in-memory cache

        Args:
            user_id: User ID
            user_info: User information
        """
        try:
            # Check cache size limit
            if len(self._user_cache) >= self._cache_size_limit:
                # Remove oldest cache entry
                oldest_key = next(iter(self._user_cache))
                del self._user_cache[oldest_key]

            self._user_cache[user_id] = user_info

        except Exception as e:
            asyncio.create_task(func.report_error(e, "Failed to update user cache"))

    def clear_cache(self):
        """Clear the in-memory user cache."""
        self._user_cache.clear()
        self.logger.info("User cache cleared")

    async def cleanup_inactive_users(self, days: int = 365) -> int:
        """Clean up inactive user data

        Args:
            days: Inactive days threshold

        Returns:
            int: Number of users cleaned up
        """
        try:
            with self.db_manager.get_connection() as conn:
                # Query users to be cleaned up
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM users 
                    WHERE last_active < datetime('now', '-{} days')
                    OR last_active IS NULL
                """.format(days))

                count = cursor.fetchone()[0]

                if count > 0:
                    # Delete inactive users
                    conn.execute("""
                        DELETE FROM users 
                        WHERE last_active < datetime('now', '-{} days')
                        OR last_active IS NULL
                    """.format(days))

                    conn.commit()
                    self.logger.info(f"Cleaned up {count} inactive users")
 
                # clear cache
                self.clear_cache()
 
                return count
 
        except Exception as e:
            await func.report_error(e, "Failed to cleanup inactive users")
            return 0


# Helper function
def extract_participant_ids(message, conversation_history: List[Any]) -> set:
    """Extract participant IDs from a message and recent conversation history.
 
    Args:
        message: Discord message object
        conversation_history: list of recent messages or dicts representing messages
 
    Returns:
        set: set of participant ID strings
    """
    participant_ids = set()
 
    # current message author
    if hasattr(message, "author") and getattr(message.author, "id", None) is not None:
        participant_ids.add(str(message.author.id))
 
    # mentions in the message
    if hasattr(message, "mentions"):
        for mention in message.mentions:
            # mention may be an object with `id` or a plain value
            mention_id = getattr(mention, "id", None)
            if mention_id is None:
                try:
                    mention_id = mention
                except Exception:
                    continue
            participant_ids.add(str(mention_id))
 
    # recent conversation history (handle both dicts and objects)
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