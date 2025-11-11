"""Database schema creation for the memory cog.

Contains SQL statements to create required tables and indexes, and performs
small migrations if needed.

All comments and logs are written in English per project rules.
"""
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def create_tables(conn: sqlite3.Connection) -> None:
    """Create necessary tables and indexes on the provided SQLite connection.

    This mirrors the previous implementation in DatabaseManager._create_tables.
    """
    cursor = conn.cursor()
    # Table for storing user information
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            discord_id TEXT PRIMARY KEY,
            discord_name TEXT,
            display_names TEXT, -- JSON array of nicknames
            procedural_memory TEXT,
            user_background TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    # Table for storing user profiles (e.g., custom system prompts)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            profile_data TEXT,
            updated_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        )
        """
    )
    # Table for pending messages to be processed by the LLM
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            timestamp REAL NOT NULL,
            processed INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_messages_processed ON pending_messages (processed)")

    # Table for storing full message content for vectorization
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp REAL NOT NULL,
            reactions TEXT,
            vectorized INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    # Migrate older schemas that lack 'vectorized' column:
    try:
        cols = [r["name"] for r in cursor.execute("PRAGMA table_info('messages')").fetchall()]
        if "vectorized" not in cols:
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN vectorized INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                # Fallback if NOT NULL with default is not accepted by this SQLite build
                cursor.execute("ALTER TABLE messages ADD COLUMN vectorized INTEGER DEFAULT 0")
    except Exception as e:
        # Log migration warning and continue; further operations will surface errors if any
        logger.warning("Failed to ensure 'vectorized' column exists: %s", e)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_vectorized ON messages (vectorized)")

    # Archive table for vectorized messages (store archived copies without vector flag)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages_archive (
            message_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp REAL NOT NULL,
            reactions TEXT,
            archived_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_archive_user_id ON messages_archive (user_id)")

    # Table for system configuration
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    logger.info("Database tables created or verified successfully.")