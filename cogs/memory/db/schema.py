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