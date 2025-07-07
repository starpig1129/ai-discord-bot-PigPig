import sqlite3
import json
import os
import logging
from pathlib import Path
from typing import Optional, List
import threading

from .models import StoryWorld, StoryCharacter, StoryInstance, PlayerRelationship


class CharacterDB:
    """Handles all database operations for characters, independent of story worlds."""

    def __init__(self):
        self.db_path = Path("data/story/characters.db")
        self._initialized = False
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        os.makedirs(self.db_path.parent, exist_ok=True)
        self.logger.info(f"CharacterDB instance created, Path: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Establishes and returns a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self):
        """Initializes the character database, creates the table, and handles migrations."""
        with self._lock:
            if self._initialized:
                return
            
            self.logger.info("Initializing CharacterDB...")
            try:
                with self._get_connection() as db:
                    # Create table if it doesn't exist
                    db.execute("""
                        CREATE TABLE IF NOT EXISTS characters (
                            character_id TEXT PRIMARY KEY,
                            name TEXT,
                            description TEXT,
                            guild_id INTEGER,
                            is_pc BOOLEAN,
                            user_id INTEGER,
                            webhook_url TEXT,
                            attributes TEXT,
                            inventory TEXT,
                            status TEXT
                        )
                    """)
                    
                    # Migration: Add new columns if they don't exist
                    cursor = db.execute("PRAGMA table_info(characters)")
                    columns = [row['name'] for row in cursor.fetchall()]
                    
                    if 'creator_id' not in columns:
                        self.logger.info("Migrating characters table: Adding 'creator_id' column.")
                        db.execute("ALTER TABLE characters ADD COLUMN creator_id INTEGER;")
                    
                    if 'is_public' not in columns:
                        self.logger.info("Migrating characters table: Adding 'is_public' column.")
                        db.execute("ALTER TABLE characters ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT 1;")

                    db.commit()
                    self._initialized = True
                    self.logger.info("CharacterDB initialized and migrated successfully.")
            except Exception as e:
                self.logger.error(f"CharacterDB initialization or migration failed: {e}")
                raise

    def save_character(self, character: StoryCharacter):
        """Saves or updates a character."""
        with self._get_connection() as db:
            db.execute(
                """
                INSERT INTO characters (character_id, name, description, guild_id, is_pc, user_id, creator_id, is_public, webhook_url, attributes, inventory, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(character_id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    guild_id=excluded.guild_id,
                    webhook_url=excluded.webhook_url,
                    attributes=excluded.attributes,
                    inventory=excluded.inventory,
                    status=excluded.status,
                    creator_id=excluded.creator_id,
                    is_public=excluded.is_public
                """,
                (
                    character.character_id,
                    character.name,
                    character.description,
                    character.guild_id,
                    character.is_pc,
                    character.user_id,
                    character.creator_id,
                    character.is_public,
                    character.webhook_url,
                    json.dumps(character.attributes),
                    json.dumps(character.inventory),
                    character.status,
                ),
            )
            db.commit()

    def _row_to_character(self, row: sqlite3.Row) -> StoryCharacter:
        """Converts a database row to a StoryCharacter object."""
        return StoryCharacter(
            name=row['name'],
            description=row['description'],
            guild_id=row['guild_id'],
            is_pc=row['is_pc'],
            user_id=row['user_id'],
            creator_id=row['creator_id'],
            is_public=bool(row['is_public']),
            webhook_url=row['webhook_url'],
            attributes=json.loads(row['attributes']),
            inventory=json.loads(row['inventory']),
            status=row['status'],
            character_id=row['character_id'],
        )

    def get_character(self, character_id: str) -> Optional[StoryCharacter]:
        """Retrieves a character by ID."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT * FROM characters WHERE character_id = ?",
                (character_id,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_character(row)
            return None

    def get_characters_by_user(self, user_id: int, guild_id: int) -> List[StoryCharacter]:
        """Retrieves all characters created by a user in a specific guild."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT * FROM characters WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            )
            rows = cursor.fetchall()
            return [self._row_to_character(row) for row in rows]

    def get_characters_by_guild(self, guild_id: int) -> List[StoryCharacter]:
        """Retrieves all characters for a specific guild."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT * FROM characters WHERE guild_id = ?",
                (guild_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_character(row) for row in rows]

    def get_selectable_characters(self, guild_id: int, user_id: int) -> List[StoryCharacter]:
        """
        Retrieves all characters that a user can select in a guild.

        This includes all public characters in the guild and all private characters
        created by the user.
        """
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT * FROM characters WHERE guild_id = ? AND (is_public = 1 OR creator_id = ?)",
                (guild_id, user_id),
            )
            rows = cursor.fetchall()
            return [self._row_to_character(row) for row in rows]

    def delete_character(self, character_id: str):
        """Deletes a character by ID."""
        with self._get_connection() as db:
            db.execute("DELETE FROM characters WHERE character_id = ?", (character_id,))
            db.commit()


class StoryDB:
    """Handles all database operations for the story module (worlds and instances)."""

    def __init__(self, guild_id: int):
        self.db_path = Path(f"data/story/{guild_id}_story.db")
        self.guild_id = guild_id
        self._initialized = False
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        os.makedirs(self.db_path.parent, exist_ok=True)
        self.logger.info(f"StoryDB instance created - Guild: {guild_id}, Path: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Establishes and returns a database connection."""
        self.logger.debug(f"Creating new DB connection - Guild: {self.guild_id}, Path: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self):
        """Initializes the database and creates tables if they don't exist."""
        with self._lock:
            if self._initialized:
                self.logger.warning(f"Database already initialized, skipping. - Guild: {self.guild_id}")
                return
            
            self.logger.info(f"Initializing database - Guild: {self.guild_id}")
            try:
                with self._get_connection() as db:
                    # V5 Schema: Use an auto-incrementing ID for the primary key
                    # and remove redundant guild_id.
                    db.execute("""
                        CREATE TABLE IF NOT EXISTS worlds (
                            id INTEGER PRIMARY KEY,
                            world_name TEXT NOT NULL UNIQUE,
                            locations TEXT,
                            attributes TEXT
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
                            active_character_ids TEXT,
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
                            FOREIGN KEY (story_id) REFERENCES instances (channel_id)
                        )
                    """)
                    db.commit()
                    self._initialized = True
                    self.logger.info(f"Database initialization complete - Guild: {self.guild_id}")
            except Exception as e:
                self.logger.error(f"Database initialization failed - Guild: {self.guild_id}, Error: {e}")
                raise

    def save_world(self, world: StoryWorld):
        """Saves or updates a story world using a SELECT then INSERT/UPDATE strategy."""
        from .models import Location, Event
        locations_data = []
        for loc in world.locations:
            events_data = [vars(event) for event in loc.events]
            loc_data = vars(loc)
            loc_data['events'] = events_data
            locations_data.append(loc_data)

        locations_json = json.dumps(locations_data)
        attributes_json = json.dumps(world.attributes)

        with self._get_connection() as db:
            cursor = db.execute("SELECT id FROM worlds WHERE world_name = ?", (world.world_name,))
            existing_world = cursor.fetchone()

            if existing_world:
                # Update existing world
                db.execute(
                    """
                    UPDATE worlds SET locations = ?, attributes = ?
                    WHERE world_name = ?
                    """,
                    (locations_json, attributes_json, world.world_name),
                )
                self.logger.info(f"Updated existing world: {world.world_name}")
            else:
                # Insert new world
                db.execute(
                    """
                    INSERT INTO worlds (world_name, locations, attributes)
                    VALUES (?, ?, ?)
                    """,
                    (world.world_name, locations_json, attributes_json),
                )
                self.logger.info(f"Saved new world: {world.world_name}")
            db.commit()

    def get_world(self, world_name: str) -> Optional[StoryWorld]:
        """Retrieves a story world by name."""
        from .models import Location, Event
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT world_name, locations, attributes FROM worlds WHERE world_name = ?",
                (world_name,),
            )
            row = cursor.fetchone()
            if row:
                locations_data = json.loads(row['locations']) if row['locations'] else []
                locations = []
                for loc_data in locations_data:
                    events_data = loc_data.pop('events', [])
                    events = [Event(**evt_data) for evt_data in events_data]
                    locations.append(Location(events=events, **loc_data))

                world = StoryWorld(
                    guild_id=self.guild_id,
                    world_name=row['world_name'],
                    locations=locations,
                    attributes=json.loads(row['attributes']) if row['attributes'] else {}
                )
                return world
            return None

    def get_all_worlds(self) -> List[StoryWorld]:
        """Retrieves all story worlds for this guild."""
        from .models import Location, Event
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT world_name, locations, attributes FROM worlds ORDER BY world_name"
            )
            rows = cursor.fetchall()
            worlds = []
            for row in rows:
                locations_data = json.loads(row['locations']) if row['locations'] else []
                locations = []
                for loc_data in locations_data:
                    events_data = loc_data.pop('events', [])
                    events = [Event(**evt_data) for evt_data in events_data]
                    locations.append(Location(events=events, **loc_data))

                worlds.append(StoryWorld(
                    guild_id=self.guild_id,
                    world_name=row['world_name'],
                    locations=locations,
                    attributes=json.loads(row['attributes']) if row['attributes'] else {}
                ))
            return worlds

    def save_story_instance(self, instance: StoryInstance):
        """Saves or updates a story instance."""
        with self._get_connection() as db:
            db.execute(
                """
                INSERT INTO instances (channel_id, guild_id, world_name, is_active, current_date, current_time, current_location, active_character_ids, current_state, event_log)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    world_name=excluded.world_name,
                    is_active=excluded.is_active,
                    current_date=excluded.current_date,
                    current_time=excluded.current_time,
                    current_location=excluded.current_location,
                    active_character_ids=excluded.active_character_ids,
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
                    json.dumps(instance.active_character_ids),
                    json.dumps(instance.current_state),
                    json.dumps(instance.event_log),
                ),
            )
            db.commit()

    def get_story_instance(self, channel_id: int) -> Optional[StoryInstance]:
        """Retrieves a story instance by channel ID."""
        with self._get_connection() as db:
            cursor = db.execute(
                "SELECT channel_id, guild_id, world_name, is_active, current_date, current_time, current_location, active_character_ids, current_state, event_log FROM instances WHERE channel_id = ?",
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
                    active_character_ids=json.loads(row['active_character_ids']),
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