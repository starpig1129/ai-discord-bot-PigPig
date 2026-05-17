import os
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
import re

ROOT_DIR = "/media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot"
STATS_DB = os.path.join(ROOT_DIR, "data", "stats", "stats.db")

# Regex to extract guild ID from LLM logs
GUILD_RE = re.compile(r"for guild: (\d+)")

def setup_db():
    os.makedirs(os.path.dirname(STATS_DB), exist_ok=True)
    conn = sqlite3.connect(STATS_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS message_events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id    TEXT    NOT NULL,
        user_id     TEXT    NOT NULL,
        channel_id  TEXT    NOT NULL,
        timestamp   REAL    NOT NULL
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS llm_call_events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id    TEXT    NOT NULL,
        model_name  TEXT    NOT NULL,
        timestamp   REAL    NOT NULL,
        duration_ms REAL    NOT NULL DEFAULT 0,
        success     INTEGER NOT NULL DEFAULT 1
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS command_events (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id      TEXT    NOT NULL,
        user_id       TEXT    NOT NULL,
        command_name  TEXT    NOT NULL,
        timestamp     REAL    NOT NULL
    )""")
    
    # Indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_msg_ts ON message_events(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_ts ON llm_call_events(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cmd_ts ON command_events(timestamp)")
    
    conn.commit()
    return conn

def parse_logs():
    conn = setup_db()
    cursor = conn.cursor()
    
    # Clear existing events if we want a fresh start? 
    # User might want to append, but usually "reconstruct" means fresh.
    # We'll just append for now to be safe, or user can delete DB manually.
    
    logs_root = Path(ROOT_DIR) / "logs"
    print(f"Scanning logs in {logs_root}...")
    
    msg_count = 0
    llm_count = 0
    
    # 1. Process Guild Logs (Messages)
    guild_dirs = [d for d in logs_root.iterdir() if d.is_dir() and d.name.isdigit()]
    for guild_dir in guild_dirs:
        guild_id = guild_dir.name
        print(f"Processing guild {guild_id}...")
        
        for date_dir in sorted(guild_dir.iterdir()):
            if not date_dir.is_dir(): continue
            info_path = date_dir / "info.jsonl"
            if not info_path.exists(): continue
            
            batch = []
            with open(info_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("action") == "receive_message":
                            user_id = record.get("user_id", "0")
                            channel_id = str(record.get("extra", {}).get("channel_id", "0"))
                            ts_str = record.get("timestamp")
                            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            ts = dt.timestamp()
                            batch.append((guild_id, user_id, channel_id, ts))
                    except Exception:
                        continue
            
            if batch:
                cursor.executemany(
                    "INSERT INTO message_events (guild_id, user_id, channel_id, timestamp) VALUES (?, ?, ?, ?)",
                    batch
                )
                msg_count += len(batch)
                conn.commit()

    # 2. Process Bot Logs (LLM Calls)
    bot_log_root = logs_root / "Bot"
    if bot_log_root.exists():
        print("Processing Bot logs for LLM calls...")
        for date_dir in sorted(bot_log_root.iterdir()):
            if not date_dir.is_dir(): continue
            info_path = date_dir / "info.jsonl"
            if not info_path.exists(): continue
            
            batch = []
            with open(info_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        # Pattern 1: llm.send_message with guild ID
                        if record.get("source") == "llm.send_message":
                            msg = record.get("message", "")
                            match = GUILD_RE.search(msg)
                            if match:
                                guild_id = match.group(1)
                                ts_str = record.get("timestamp")
                                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                ts = dt.timestamp()
                                # Best effort: model name is unknown in old logs, use "historical"
                                batch.append((guild_id, "historical", ts, 0, 1))
                    except Exception:
                        continue
            
            if batch:
                cursor.executemany(
                    "INSERT INTO llm_call_events (guild_id, model_name, timestamp, duration_ms, success) VALUES (?, ?, ?, ?, ?)",
                    batch
                )
                llm_count += len(batch)
                conn.commit()

    print(f"Finished. Reconstructed {msg_count} message events and {llm_count} LLM call events.")
    conn.close()

if __name__ == "__main__":
    parse_logs()
