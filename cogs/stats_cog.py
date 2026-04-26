"""StatsCog: real-time user statistics tracking and historical log migration.

Listens for on_message events to update per-user stats in the user_stats
table, and runs a low-priority background task on cog load to ingest
historical NDJSON log files.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from discord.ext import commands

from addons.logging import get_logger
from cogs.memory.db.stats_storage import StatsStorage
from function import func, ROOT_DIR

logger = get_logger(server_id="system", source=__name__)


class StatsCog(commands.Cog):
    """Real-time user stats tracking and historical log migration.

    Attributes:
        bot: The Discord bot instance.
        stats_storage: StatsStorage instance for DB operations.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize StatsCog.

        Obtains a DatabaseConnection from the bot's procedural_storage
        and creates a StatsStorage instance.

        Args:
            bot: The Discord bot instance.
        """
        self.bot = bot
        self.stats_storage: Optional[StatsStorage] = None
        self._migration_task: Optional[asyncio.Task] = None

        # Obtain DB connection from procedural_storage (same DB as users table)
        procedural_storage = getattr(bot, "procedural_storage", None)
        if procedural_storage:
            db_conn = getattr(procedural_storage, "db", None)
            if db_conn:
                self.stats_storage = StatsStorage(db_conn)
                logger.info("StatsStorage initialized from procedural_storage.")
            else:
                logger.warning(
                    "procedural_storage has no 'db' attribute; "
                    "StatsCog will not track stats."
                )
        else:
            logger.warning(
                "Bot has no procedural_storage; StatsCog will not track stats."
            )

    async def cog_load(self) -> None:
        """Start background log migration task when cog loads."""
        if self.stats_storage:
            self._migration_task = asyncio.create_task(
                self._migrate_logs_background()
            )
            logger.info("Background log migration task scheduled.")

    async def cog_unload(self) -> None:
        """Cancel background migration task on cog unload."""
        if self._migration_task and not self._migration_task.done():
            self._migration_task.cancel()
            logger.info("Background log migration task cancelled.")

    # ------------------------------------------------------------------
    # Real-time on_message listener
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message) -> None:
        """Update user stats for every incoming message.

        Args:
            message: The Discord message object.
        """
        # Skip bot messages and DMs
        if not message.guild or message.author.bot:
            return
        if not self.stats_storage:
            return

        try:
            user_id = str(message.author.id)
            guild_id = str(message.guild.id)
            channel_name = getattr(message.channel, "name", "unknown")
            timestamp = (
                message.created_at.isoformat()
                if message.created_at
                else datetime.now(timezone.utc).isoformat()
            )
            content = message.content or ""

            # Use asyncio.shield to prevent task cancellation from
            # interrupting the DB write mid-transaction
            await asyncio.shield(
                self.stats_storage.upsert_user_stats(
                    user_id=user_id,
                    guild_id=guild_id,
                    message_content=content,
                    channel_name=channel_name,
                    timestamp=timestamp,
                )
            )
        except Exception as e:
            # Non-critical: log and continue; do not break message flow
            logger.warning(
                "StatsCog on_message stats update failed: %s", e
            )

    # ------------------------------------------------------------------
    # Background historical log migration
    # ------------------------------------------------------------------

    async def _migrate_logs_background(self) -> None:
        """Ingest historical NDJSON log files into user_stats.

        Processes logs/{guild_id}/{YYYYMMDD}/info.jsonl files that have
        not been processed yet (tracked via log_migration_state table).

        Performance safeguards:
        - Reads NDJSON line-by-line (no full file loads)
        - Commits every 500 records
        - Yields event loop every batch (asyncio.sleep(0))
        - Sleeps 30s between each day directory
        """
        if not self.stats_storage:
            return

        # Wait for bot to be fully ready before starting migration
        await self.bot.wait_until_ready()
        # Small initial delay to avoid competing with startup I/O
        await asyncio.sleep(10)

        logs_root = Path(ROOT_DIR) / "logs"
        if not logs_root.is_dir():
            logger.info("No logs/ directory found; skipping migration.")
            return

        logger.info("Starting background log migration from %s", logs_root)

        try:
            # Find all guild_id directories (numeric names only)
            guild_dirs = sorted(
                d for d in logs_root.iterdir()
                if d.is_dir() and d.name.isdigit()
            )

            for guild_dir in guild_dirs:
                guild_id = guild_dir.name
                try:
                    await self._migrate_guild_logs(guild_id, guild_dir)
                except asyncio.CancelledError:
                    logger.info("Migration cancelled for guild %s", guild_id)
                    return
                except Exception as e:
                    logger.error(
                        "Migration failed for guild %s: %s", guild_id, e
                    )
                    await func.report_error(
                        e, f"Log migration failed for guild {guild_id}"
                    )
                    continue

            logger.info("Background log migration completed for all guilds.")
        except asyncio.CancelledError:
            logger.info("Background log migration task was cancelled.")
        except Exception as e:
            logger.error("Background log migration encountered error: %s", e)
            await func.report_error(e, "Background log migration failed")

    async def _migrate_guild_logs(
        self, guild_id: str, guild_dir: Path
    ) -> None:
        """Migrate log files for a single guild.

        Args:
            guild_id: The guild's Discord snowflake ID.
            guild_dir: Path to the guild's log directory.
        """
        # Get last processed date
        last_processed = await self.stats_storage.get_migration_state(guild_id)

        # Find date directories (YYYYMMDD format)
        date_dirs = sorted(
            d for d in guild_dir.iterdir()
            if d.is_dir() and len(d.name) == 8 and d.name.isdigit()
        )

        if not date_dirs:
            return

        processed_count = 0

        for date_dir in date_dirs:
            date_str = date_dir.name

            # Skip already-processed dates
            if last_processed and date_str <= last_processed:
                continue

            jsonl_path = date_dir / "info.jsonl"
            if not jsonl_path.is_file():
                continue

            logger.info(
                "Migrating logs for guild=%s date=%s", guild_id, date_str
            )

            batch_count = 0
            batch_records = []
            try:
                with open(jsonl_path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Only process actual user messages
                        if record.get("action") != "receive_message":
                            continue

                        user_id = record.get("user_id", "")
                        if not user_id:
                            continue

                        channel_name = record.get("channel_or_file", "unknown")
                        timestamp = record.get(
                            "timestamp",
                            datetime.now(timezone.utc).isoformat(),
                        )
                        content = record.get("message", "")

                        batch_records.append({
                            "user_id": user_id,
                            "guild_id": guild_id,
                            "message_content": content,
                            "channel_name": channel_name,
                            "timestamp": timestamp,
                        })

                        batch_count += 1
                        processed_count += 1

                        # Yield event loop every 500 records
                        if len(batch_records) >= 500:
                            await self.stats_storage.bulk_upsert_user_stats(batch_records)
                            batch_records.clear()
                            await asyncio.sleep(0)
                            logger.debug(
                                "Migration progress: guild=%s date=%s "
                                "processed=%d",
                                guild_id,
                                date_str,
                                batch_count,
                            )
                            
                    # Process any remaining records
                    if batch_records:
                        await self.stats_storage.bulk_upsert_user_stats(batch_records)
                        batch_records.clear()

            except Exception as e:
                logger.error(
                    "Error reading %s: %s", jsonl_path, e
                )
                await func.report_error(
                    e, f"Log migration read error: {jsonl_path}"
                )
                continue

            # Mark this date as processed
            await self.stats_storage.set_migration_state(guild_id, date_str)
            logger.info(
                "Completed migration for guild=%s date=%s (%d records)",
                guild_id,
                date_str,
                batch_count,
            )

            # Sleep between days to avoid I/O contention
            await asyncio.sleep(30)

        if processed_count > 0:
            logger.info(
                "Guild %s migration complete: %d total records processed.",
                guild_id,
                processed_count,
            )


async def setup(bot: commands.Bot) -> None:
    """Register StatsCog with the bot.

    Args:
        bot: The Discord bot instance.
    """
    await bot.add_cog(StatsCog(bot))
