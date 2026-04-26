"""Database schema creation for the memory cog.

Contains SQL statements to create required tables and indexes, and performs
small migrations if needed.

All comments and logs are written in English per project rules.
"""
import sqlite3
from typing import Any
from addons.logging import get_logger
logger = get_logger(server_id="system", source=__name__)


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
            user_id TEXT PRIMARY KEY,
            profile_data TEXT,
            updated_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (discord_id) ON DELETE CASCADE
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

    # Table for Guild and Channel Knowledge (Internal Memes, Relationships, etc.)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge (
            target_type TEXT, -- 'guild' or 'channel'
            target_id TEXT,
            content TEXT, -- Stored as a structured text block managed by AI Merge
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (target_type, target_id)
        );
        """
    )
    # Table for cumulative user statistics (per user × per guild)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            total_messages INTEGER NOT NULL DEFAULT 0,
            active_hours TEXT NOT NULL DEFAULT '{}',
            top_channels TEXT NOT NULL DEFAULT '{}',
            top_emojis TEXT NOT NULL DEFAULT '{}',
            top_words TEXT NOT NULL DEFAULT '{}',
            streak_days INTEGER NOT NULL DEFAULT 0,
            streak_last_date TEXT,
            last_active_at DATETIME,
            first_message_at DATETIME,
            PRIMARY KEY (user_id, guild_id)
        );
        """
    )

    # Table for tracking historical log migration progress
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS log_migration_state (
            guild_id TEXT PRIMARY KEY,
            last_processed_date TEXT NOT NULL
        );
        """
    )

    logger.info("Database tables created or verified successfully.")