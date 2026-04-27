"""StatsStorage: handles user statistics and log migration state persistence.

This module provides CRUD operations for the user_stats and
log_migration_state tables, supporting real-time message tracking and
historical log migration.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Set

from .connection import DatabaseConnection
from function import func
from addons.logging import get_logger

logger = get_logger(server_id="system", source=__name__)

# ---------------------------------------------------------------------------
# Chinese / CJK stop-words (compact set for jieba filtering)
# ---------------------------------------------------------------------------
_STOP_WORDS: Set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一個", "上", "也", "很", "到", "說", "要", "去", "你", "會", "著",
    "沒有", "看", "好", "自己", "這", "他", "她", "它", "麼", "嗎", "吧",
    "啊", "嗯", "喔", "欸", "耶", "呢", "哦", "哈", "噢", "呀", "唉",
    "把", "讓", "被", "從", "而", "且", "但", "跟", "對", "所以", "因為",
    "如果", "那", "還", "比", "這個", "那個", "什麼", "怎麼", "可以",
    "沒", "能", "已經", "過", "之", "等", "多", "時", "個", "可", "來",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "am",
    "do", "did", "does", "i", "you", "he", "she", "it", "we", "they",
    "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "that", "this", "not", "no", "so", "if", "my", "me", "your",
}

# Regex for extracting emoji (both Unicode and Discord custom <:name:id>)
_UNICODE_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)
_DISCORD_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")

# Maximum number of words to keep in top_words to prevent unbounded growth
_MAX_TOP_WORDS = 200


class StatsStorage:
    """Handles user_stats and log_migration_state table operations.

    Attributes:
        db: The shared DatabaseConnection instance.
    """

    def __init__(self, db: DatabaseConnection) -> None:
        """Initialize with a DatabaseConnection instance.

        Args:
            db: The shared SQLite connection manager.
        """
        self.db = db
        self.logger = logger

    # ------------------------------------------------------------------
    # user_stats CRUD
    # ------------------------------------------------------------------

    async def get_user_stats(
        self, user_id: str, guild_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cumulative stats for a user in a guild.

        Args:
            user_id: Discord user snowflake ID.
            guild_id: Discord guild snowflake ID.

        Returns:
            A dict with all stat columns, or None if no record exists.
            JSON columns are returned as parsed Python dicts.
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM user_stats WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                result = dict(row)
                # Parse JSON text columns into dicts
                for key in ("active_hours", "top_channels", "top_emojis", "top_words"):
                    raw = result.get(key, "{}")
                    try:
                        result[key] = json.loads(raw) if raw else {}
                    except (json.JSONDecodeError, TypeError):
                        result[key] = {}
                return result
        except Exception as e:
            await func.report_error(
                e, f"get_user_stats failed (user={user_id}, guild={guild_id})"
            )
            return None

    async def upsert_user_stats(
        self,
        user_id: str,
        guild_id: str,
        message_content: str,
        channel_name: str,
        timestamp: str,
    ) -> None:
        """Insert or update cumulative stats for a single message event.

        This performs an atomic read-modify-write cycle:
        1. Read existing row (if any).
        2. Merge deltas into JSON columns in Python.
        3. Write back via INSERT ... ON CONFLICT DO UPDATE.

        Args:
            user_id: Discord user snowflake ID.
            guild_id: Discord guild snowflake ID.
            message_content: The raw message text (used for jieba + emoji extraction).
            channel_name: The channel name where the message was sent.
            timestamp: ISO-8601 formatted timestamp string.
        """
        try:
            # Parse timestamp
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                dt = datetime.utcnow()

            hour_key = str(dt.hour)
            today_str = dt.strftime("%Y-%m-%d")

            # Extract emojis
            emojis = _extract_emojis(message_content)

            # Segment words with jieba
            words = _segment_words(message_content)

            with self.db.get_connection() as conn:
                # Read existing row
                cursor = conn.execute(
                    "SELECT * FROM user_stats WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                existing = cursor.fetchone()

                if existing:
                    row = dict(existing)
                    total = row.get("total_messages", 0) + 1

                    # Merge JSON fields
                    active_hours = _safe_json_load(row.get("active_hours", "{}"))
                    active_hours[hour_key] = active_hours.get(hour_key, 0) + 1

                    top_channels = _safe_json_load(row.get("top_channels", "{}"))
                    if channel_name:
                        top_channels[channel_name] = (
                            top_channels.get(channel_name, 0) + 1
                        )

                    top_emojis = _safe_json_load(row.get("top_emojis", "{}"))
                    for em in emojis:
                        top_emojis[em] = top_emojis.get(em, 0) + 1

                    top_words_dict = _safe_json_load(row.get("top_words", "{}"))
                    for w in words:
                        top_words_dict[w] = top_words_dict.get(w, 0) + 1
                    top_words_dict = _trim_top_words(top_words_dict)

                    # Streak calculation
                    streak_last = row.get("streak_last_date")
                    streak_days = row.get("streak_days", 0)
                    streak_days, streak_last_date = _compute_streak(
                        streak_days, streak_last, today_str
                    )

                    first_message_at = row.get("first_message_at") or timestamp

                    conn.execute(
                        """
                        UPDATE user_stats SET
                            total_messages = ?,
                            active_hours = ?,
                            top_channels = ?,
                            top_emojis = ?,
                            top_words = ?,
                            streak_days = ?,
                            streak_last_date = ?,
                            last_active_at = ?,
                            first_message_at = ?
                        WHERE user_id = ? AND guild_id = ?
                        """,
                        (
                            total,
                            json.dumps(active_hours, ensure_ascii=False),
                            json.dumps(top_channels, ensure_ascii=False),
                            json.dumps(top_emojis, ensure_ascii=False),
                            json.dumps(top_words_dict, ensure_ascii=False),
                            streak_days,
                            streak_last_date,
                            timestamp,
                            first_message_at,
                            user_id,
                            guild_id,
                        ),
                    )
                else:
                    # First message ever for this user in this guild
                    active_hours = {hour_key: 1}
                    top_channels = {channel_name: 1} if channel_name else {}
                    top_emojis_dict = dict(Counter(emojis))
                    top_words_dict = dict(Counter(words))
                    top_words_dict = _trim_top_words(top_words_dict)

                    conn.execute(
                        """
                        INSERT INTO user_stats (
                            user_id, guild_id, total_messages,
                            active_hours, top_channels, top_emojis, top_words,
                            streak_days, streak_last_date,
                            last_active_at, first_message_at
                        ) VALUES (?, ?, 1, ?, ?, ?, ?, 1, ?, ?, ?)
                        """,
                        (
                            user_id,
                            guild_id,
                            json.dumps(active_hours, ensure_ascii=False),
                            json.dumps(top_channels, ensure_ascii=False),
                            json.dumps(top_emojis_dict, ensure_ascii=False),
                            json.dumps(top_words_dict, ensure_ascii=False),
                            today_str,
                            timestamp,
                            timestamp,
                        ),
                    )
                conn.commit()
        except Exception as e:
            await func.report_error(
                e,
                f"upsert_user_stats failed (user={user_id}, guild={guild_id})",
            )

    async def bulk_upsert_user_stats(self, records: List[Dict[str, Any]]) -> None:
        """Insert or update cumulative stats for a batch of message events.

        Args:
            records: A list of dicts, each containing:
                - user_id: str
                - guild_id: str
                - message_content: str
                - channel_name: str
                - timestamp: str
        """
        if not records:
            return

        try:
            with self.db.get_connection() as conn:
                for rec in records:
                    user_id = rec["user_id"]
                    guild_id = rec["guild_id"]
                    message_content = rec["message_content"]
                    channel_name = rec["channel_name"]
                    timestamp = rec["timestamp"]

                    try:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        dt = datetime.utcnow()

                    hour_key = str(dt.hour)
                    today_str = dt.strftime("%Y-%m-%d")

                    emojis = _extract_emojis(message_content)
                    words = _segment_words(message_content)

                    cursor = conn.execute(
                        "SELECT * FROM user_stats WHERE user_id = ? AND guild_id = ?",
                        (user_id, guild_id),
                    )
                    existing = cursor.fetchone()

                    if existing:
                        row = dict(existing)
                        total = row.get("total_messages", 0) + 1

                        active_hours = _safe_json_load(row.get("active_hours", "{}"))
                        active_hours[hour_key] = active_hours.get(hour_key, 0) + 1

                        top_channels = _safe_json_load(row.get("top_channels", "{}"))
                        if channel_name:
                            top_channels[channel_name] = (
                                top_channels.get(channel_name, 0) + 1
                            )

                        top_emojis = _safe_json_load(row.get("top_emojis", "{}"))
                        for em in emojis:
                            top_emojis[em] = top_emojis.get(em, 0) + 1

                        top_words_dict = _safe_json_load(row.get("top_words", "{}"))
                        for w in words:
                            top_words_dict[w] = top_words_dict.get(w, 0) + 1
                        top_words_dict = _trim_top_words(top_words_dict)

                        streak_last = row.get("streak_last_date")
                        streak_days = row.get("streak_days", 0)
                        streak_days, streak_last_date = _compute_streak(
                            streak_days, streak_last, today_str
                        )

                        first_message_at = row.get("first_message_at") or timestamp

                        conn.execute(
                            """
                            UPDATE user_stats SET
                                total_messages = ?,
                                active_hours = ?,
                                top_channels = ?,
                                top_emojis = ?,
                                top_words = ?,
                                streak_days = ?,
                                streak_last_date = ?,
                                last_active_at = ?,
                                first_message_at = ?
                            WHERE user_id = ? AND guild_id = ?
                            """,
                            (
                                total,
                                json.dumps(active_hours, ensure_ascii=False),
                                json.dumps(top_channels, ensure_ascii=False),
                                json.dumps(top_emojis, ensure_ascii=False),
                                json.dumps(top_words_dict, ensure_ascii=False),
                                streak_days,
                                streak_last_date,
                                timestamp,
                                first_message_at,
                                user_id,
                                guild_id,
                            ),
                        )
                    else:
                        active_hours = {hour_key: 1}
                        top_channels = {channel_name: 1} if channel_name else {}
                        top_emojis_dict = dict(Counter(emojis))
                        top_words_dict = dict(Counter(words))
                        top_words_dict = _trim_top_words(top_words_dict)

                        conn.execute(
                            """
                            INSERT INTO user_stats (
                                user_id, guild_id, total_messages,
                                active_hours, top_channels, top_emojis, top_words,
                                streak_days, streak_last_date,
                                last_active_at, first_message_at
                            ) VALUES (?, ?, 1, ?, ?, ?, ?, 1, ?, ?, ?)
                            """,
                            (
                                user_id,
                                guild_id,
                                json.dumps(active_hours, ensure_ascii=False),
                                json.dumps(top_channels, ensure_ascii=False),
                                json.dumps(top_emojis_dict, ensure_ascii=False),
                                json.dumps(top_words_dict, ensure_ascii=False),
                                today_str,
                                timestamp,
                                timestamp,
                            ),
                        )
                # Commit once at the end of the batch
                conn.commit()
        except Exception as e:
            await func.report_error(e, "bulk_upsert_user_stats failed")

    # ------------------------------------------------------------------
    # log_migration_state CRUD
    # ------------------------------------------------------------------

    async def get_migration_state(self, guild_id: str) -> Optional[str]:
        """Get the last processed date for historical log migration.

        Args:
            guild_id: Discord guild snowflake ID.

        Returns:
            A date string in YYYYMMDD format, or None if no migration
            has been performed for this guild yet.
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT last_processed_date FROM log_migration_state WHERE guild_id = ?",
                    (guild_id,),
                )
                row = cursor.fetchone()
                return row["last_processed_date"] if row else None
        except Exception as e:
            await func.report_error(
                e, f"get_migration_state failed (guild={guild_id})"
            )
            return None

    async def set_migration_state(self, guild_id: str, date_str: str) -> None:
        """Record the last processed date for historical log migration.

        Args:
            guild_id: Discord guild snowflake ID.
            date_str: Date string in YYYYMMDD format.
        """
        try:
            with self.db.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO log_migration_state (guild_id, last_processed_date)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        last_processed_date = excluded.last_processed_date
                    """,
                    (guild_id, date_str),
                )
                conn.commit()
        except Exception as e:
            await func.report_error(
                e, f"set_migration_state failed (guild={guild_id})"
            )


# ======================================================================
# Helper functions (module-private)
# ======================================================================


def _safe_json_load(raw: Any) -> Dict[str, int]:
    """Safely parse a JSON string into a dict, defaulting to empty dict."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_emojis(text: str) -> List[str]:
    """Extract Unicode and Discord custom emojis from text."""
    if not text:
        return []
    results: List[str] = []
    # Unicode emojis
    for match in _UNICODE_EMOJI_RE.finditer(text):
        # Each character in the match is a separate emoji
        for ch in match.group():
            results.append(ch)
    # Discord custom emojis  <:name:id> or <a:name:id>
    for match in _DISCORD_EMOJI_RE.finditer(text):
        results.append(match.group())
    return results


def _segment_words(text: str) -> List[str]:
    """Segment text using jieba and filter stop-words / noise.

    Returns a list of meaningful words (length >= 2, not pure digits,
    not in the stop-word set).
    """
    if not text:
        return []
    try:
        import jieba
    except ImportError:
        logger.warning("jieba not installed; skipping word segmentation.")
        return []

    # Remove URLs, mentions, and custom emoji markup before segmenting
    cleaned = re.sub(r"https?://\S+", "", text)
    cleaned = re.sub(r"<@!?\d+>", "", cleaned)
    cleaned = re.sub(r"<#\d+>", "", cleaned)
    cleaned = re.sub(r"<a?:\w+:\d+>", "", cleaned)

    words: List[str] = []
    for word in jieba.cut(cleaned):
        w = word.strip().lower()
        if len(w) < 2:
            continue
        if w.isdigit():
            continue
        if w in _STOP_WORDS:
            continue
        words.append(w)
    return words


def _trim_top_words(words_dict: Dict[str, int]) -> Dict[str, int]:
    """Keep only the top N words by frequency to prevent unbounded growth."""
    if len(words_dict) <= _MAX_TOP_WORDS:
        return words_dict
    sorted_items = sorted(words_dict.items(), key=lambda x: x[1], reverse=True)
    return dict(sorted_items[:_MAX_TOP_WORDS])


def _compute_streak(
    current_streak: int, last_date_str: Optional[str], today_str: str
) -> tuple[int, str]:
    """Compute the updated streak days based on the last active date.

    Args:
        current_streak: The current consecutive active days count.
        last_date_str: The last active date in YYYY-MM-DD format, or None.
        today_str: Today's date in YYYY-MM-DD format.

    Returns:
        A tuple of (updated_streak_days, updated_last_date_str).
    """
    if not last_date_str:
        return 1, today_str

    if last_date_str == today_str:
        # Same day, no change
        return current_streak, today_str

    try:
        last_date = date.fromisoformat(last_date_str)
        today = date.fromisoformat(today_str)
        diff = (today - last_date).days

        if diff == 1:
            # Consecutive day
            return current_streak + 1, today_str
        elif diff > 1:
            # Streak broken
            return 1, today_str
        else:
            # Negative diff (shouldn't happen), keep current
            return current_streak, last_date_str
    except (ValueError, TypeError):
        return 1, today_str
