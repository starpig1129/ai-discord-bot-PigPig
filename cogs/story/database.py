import sqlite3
import json
import os
import logging
from pathlib import Path
from typing import Optional, List
import threading

from .models import StoryWorld, StoryCharacter, StoryInstance, PlayerRelationship

class StoryDB:
    """Handles all database operations for the story module."""

    def __init__(self, guild_id: int):
        self.db_path = Path(f"data/story/{guild_id}_story.db")
        self.guild_id = guild_id
        self._initialized = False
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        os.makedirs(self.db_path.parent, exist_ok=True)
        self.logger.info(f"[DEBUG] StoryDB 實例創建 - Guild: {guild_id}, Path: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Establishes and returns a database connection."""
        self.logger.debug(f"[DEBUG] 創建新的資料庫連接 - Guild: {self.guild_id}, Path: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 讓結果可以像字典一樣訪問
        return conn

    def initialize(self):
        """Initializes the database and creates tables if they don't exist."""
        with self._lock:
            if self._initialized:
                self.logger.warning(f"[DEBUG] 資料庫已初始化，跳過重複初始化 - Guild: {self.guild_id}")
                return
            
            self.logger.info(f"[DEBUG] 開始初始化資料庫 - Guild: {self.guild_id}")
            try:
                with self._get_connection() as db:
                    db.execute("""
                        CREATE TABLE IF NOT EXISTS worlds (
                            world_name TEXT PRIMARY KEY,
                            guild_id INTEGER,
                            background TEXT,
                            rules TEXT,
                            elements TEXT
                        )
                    """)
                    db.execute("""
                        CREATE TABLE IF NOT EXISTS characters (
                            character_id TEXT PRIMARY KEY,
                            world_name TEXT,
                            name TEXT,
                            description TEXT,
                            is_pc BOOLEAN,
                            user_id INTEGER,
                            webhook_url TEXT,
                            attributes TEXT,
                            inventory TEXT,
                            status TEXT,
                            FOREIGN KEY (world_name) REFERENCES worlds (world_name)
                        )
                    """)
                    db.execute("""
                        CREATE TABLE IF NOT EXISTS instances (
                            channel_id INTEGER PRIMARY KEY,
                            guild_id INTEGER,
                            world_name TEXT,
                            is_active BOOLEAN,
                            current_date TEXT,
                            current_time TEXT,
                            current_location TEXT,
                            active_characters TEXT,
                            current_state TEXT,
                            event_log TEXT,
                            FOREIGN KEY (world_name) REFERENCES worlds (world_name)
                        )
                    """)
                    db.execute("""
                        CREATE TABLE IF NOT EXISTS player_relationships (
                            relationship_id TEXT PRIMARY KEY,
                            story_id INTEGER,
                            character_id TEXT,
                            user_id INTEGER,
                            description TEXT,
                            FOREIGN KEY (story_id) REFERENCES instances (channel_id),
                            FOREIGN KEY (character_id) REFERENCES characters (character_id)
                        )
                    """)
                    db.commit()
                    self._initialized = True
                    self.logger.info(f"[DEBUG] 資料庫初始化完成 - Guild: {self.guild_id}")
            except Exception as e:
                self.logger.error(f"[DEBUG] 資料庫初始化失敗 - Guild: {self.guild_id}, Error: {e}")
                raise

    def save_world(self, world: StoryWorld):
        """Saves or updates a story world."""
        with self._get_connection() as db:
            db.execute(
                """
                INSERT INTO worlds (world_name, guild_id, background, rules, elements)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(world_name) DO UPDATE SET
                    background=excluded.background,
                    rules=excluded.rules,
                    elements=excluded.elements
                """,
                (
                    world.world_name,
                    world.guild_id,
                    world.background,
                    json.dumps(world.rules),
                    json.dumps(world.elements),
                ),
            )
            db.commit()

    def get_world(self, world_name: str) -> Optional[StoryWorld]:
        """Retrieves a story world by name."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT guild_id, world_name, background, rules, elements FROM worlds WHERE world_name = ?",
                (world_name,),
            )
            row = cursor.fetchone()
            if row:
                return StoryWorld(
                    guild_id=row[0],
                    world_name=row[1],
                    background=row[2],
                    rules=json.loads(row[3]),
                    elements=json.loads(row[4]),
                )
            return None

    def get_all_worlds(self) -> List[StoryWorld]:
        """Retrieves all story worlds for this guild."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT guild_id, world_name, background, rules, elements FROM worlds ORDER BY world_name"
            )
            rows = cursor.fetchall()
            worlds = []
            for row in rows:
                worlds.append(StoryWorld(
                    guild_id=row[0],
                    world_name=row[1],
                    background=row[2],
                    rules=json.loads(row[3]),
                    elements=json.loads(row[4]),
                ))
            return worlds

    def save_character(self, character: StoryCharacter):
        """Saves or updates a character."""
        with self._get_connection() as db:
            db.execute(
                """
                INSERT INTO characters (character_id, world_name, name, description, is_pc, user_id, webhook_url, attributes, inventory, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(character_id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    webhook_url=excluded.webhook_url,
                    attributes=excluded.attributes,
                    inventory=excluded.inventory,
                    status=excluded.status
                """,
                (
                    character.character_id,
                    character.world_name,
                    character.name,
                    character.description,
                    character.is_pc,
                    character.user_id,
                    character.webhook_url,
                    json.dumps(character.attributes),
                    json.dumps(character.inventory),
                    character.status,
                ),
            )
            db.commit()

    def get_character(self, character_id: str) -> Optional[StoryCharacter]:
        """Retrieves a character by ID."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT world_name, name, description, is_pc, user_id, webhook_url, attributes, inventory, status, character_id FROM characters WHERE character_id = ?",
                (character_id,),
            )
            row = cursor.fetchone()
            if row:
                return StoryCharacter(
                    world_name=row['world_name'],
                    name=row['name'],
                    description=row['description'],
                    is_pc=row['is_pc'],
                    user_id=row['user_id'],
                    webhook_url=row['webhook_url'],
                    attributes=json.loads(row['attributes']),
                    inventory=json.loads(row['inventory']),
                    status=row['status'],
                    character_id=row['character_id'],
                )
            return None

    def get_characters_by_user(self, user_id: int, world_name: str) -> List[StoryCharacter]:
        """Retrieves all characters created by a user in a specific world."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT world_name, name, description, is_pc, user_id, webhook_url, attributes, inventory, status, character_id FROM characters WHERE user_id = ? AND world_name = ?",
                (user_id, world_name),
            )
            rows = cursor.fetchall()
            characters = []
            for row in rows:
                characters.append(StoryCharacter(
                    world_name=row['world_name'],
                    name=row['name'],
                    description=row['description'],
                    is_pc=row['is_pc'],
                    user_id=row['user_id'],
                    webhook_url=row['webhook_url'],
                    attributes=json.loads(row['attributes']),
                    inventory=json.loads(row['inventory']),
                    status=row['status'],
                    character_id=row['character_id'],
                ))
            return characters

    def save_story_instance(self, instance: StoryInstance):
        """Saves or updates a story instance."""
        with self._get_connection() as db:
            db.execute(
                """
                INSERT INTO instances (channel_id, guild_id, world_name, is_active, current_date, current_time, current_location, active_characters, current_state, event_log)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    world_name=excluded.world_name,
                    is_active=excluded.is_active,
                    current_date=excluded.current_date,
                    current_time=excluded.current_time,
                    current_location=excluded.current_location,
                    active_characters=excluded.active_characters,
                    current_state=excluded.current_state,
                    event_log=excluded.event_log
                """,
                (
                    instance.channel_id,
                    instance.guild_id,
                    instance.world_name,
                    instance.is_active,
                    instance.current_date,
                    instance.current_time,
                    instance.current_location,
                    json.dumps(instance.active_characters),
                    json.dumps(instance.current_state),
                    json.dumps(instance.event_log),
                ),
            )
            db.commit()

    def get_story_instance(self, channel_id: int) -> Optional[StoryInstance]:
        """Retrieves a story instance by channel ID."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT channel_id, guild_id, world_name, is_active, current_date, current_time, current_location, active_characters, current_state, event_log FROM instances WHERE channel_id = ?",
                (channel_id,),
            )
            row = cursor.fetchone()
            if row:
                return StoryInstance(
                    channel_id=row['channel_id'],
                    guild_id=row['guild_id'],
                    world_name=row['world_name'],
                    is_active=row['is_active'],
                    current_date=row['current_date'],
                    current_time=row['current_time'],
                    current_location=row['current_location'],
                    active_characters=json.loads(row['active_characters']),
                    current_state=json.loads(row['current_state']),
                    event_log=json.loads(row['event_log']),
                )
            return None

    def save_player_relationship(self, relationship: PlayerRelationship):
        """Saves or updates a player-NPC relationship."""
        with self._get_connection() as db:
            db.execute(
                """
                INSERT INTO player_relationships (relationship_id, story_id, character_id, user_id, description)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(relationship_id) DO UPDATE SET
                    description=excluded.description
                """,
                (
                    relationship.relationship_id,
                    relationship.story_id,
                    relationship.character_id,
                    relationship.user_id,
                    relationship.description,
                ),
            )
            db.commit()

    def get_player_relationship(self, relationship_id: str) -> Optional[PlayerRelationship]:
        """Retrieves a player-NPC relationship by ID."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT relationship_id, story_id, character_id, user_id, description FROM player_relationships WHERE relationship_id = ?",
                (relationship_id,),
            )
            row = cursor.fetchone()
            if row:
                return PlayerRelationship(
                    relationship_id=row['relationship_id'],
                    story_id=row['story_id'],
                    character_id=row['character_id'],
                    user_id=row['user_id'],
                    description=row['description'],
                )
            return None

    def get_relationships_for_story(self, story_id: int) -> List[PlayerRelationship]:
        """Retrieves all relationships for a given story instance."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT relationship_id, story_id, character_id, user_id, description FROM player_relationships WHERE story_id = ?",
                (story_id,),
            )
            rows = cursor.fetchall()
            return [
                PlayerRelationship(
                    relationship_id=row['relationship_id'],
                    story_id=row['story_id'],
                    character_id=row['character_id'],
                    user_id=row['user_id'],
                    description=row['description'],
                )
                for row in rows
            ]