# Story Manager Cog Documentation

## Overview

The Story Manager cog provides comprehensive story creation and management capabilities for Discord users. It enables users to create, develop, and manage interactive stories with AI assistance, collaborative story-building features, and various story formats including collaborative writing, role-playing adventures, and creative narratives.

## Features

### Core Functionality
- **Interactive Story Creation**: Create and develop stories with AI assistance
- **Collaborative Writing**: Multi-user story building and editing
- **Story Templates**: Pre-defined story frameworks and structures
- **Character Management**: Create and manage story characters
- **Chapter Organization**: Structure stories with chapters and scenes
- **Story Analytics**: Track story development and user engagement
- **Export/Import**: Save and share story files

### Key Components
- `StoryManager` class - Main cog implementation
- AI-powered story generation engine
- Collaborative editing system
- Story database and version control
- Character and world-building tools

## Commands

### `/story_create`
Creates a new story with optional template and parameters.

**Parameters**:
- `title` (string, required): Story title
- `genre` (string, optional): Story genre (fantasy, sci-fi, mystery, romance, adventure, horror, slice-of-life)
- `template` (string, optional): Story template (freeform, chapter-based, episodic, collaborative)
- `description` (string, optional): Brief story description
- `is_collaborative` (boolean, optional, default: false): Allow multiple users to contribute

**Usage Examples**:
```
/story_create title:"The Lost Kingdom" genre:"fantasy" template:"chapter-based" description:"An epic tale of a young hero discovering ancient magic"
/story_create title:"Space Adventure" genre:"sci-fi" is_collaborative:true
/story_create title:"Murder Mystery Night" genre:"mystery" template:"collaborative"
```

**Required Permissions**: None (public access)

### `/story_write`
Adds content to an existing story.

**Parameters**:
- `story_id` (string, required): ID of the story to write to
- `content` (string, required): Story content to add
- `chapter` (string, optional): Chapter name/number
- `scene` (string, optional): Scene identifier
- `perspective` (string, optional): Narrative perspective (first, third, omniscient)

**Usage Examples**:
```
/story_write story_id:"story_12345" content:"The old castle loomed in the distance..." chapter:"Chapter 1" scene:"Arrival"
/story_write story_id:"story_12345" content:"Sarah felt a chill run down her spine as she opened the ancient book." perspective:"third"
```

**Required Permissions**: None (if collaborative or owner)

### `/story_read`
Displays story content with formatting options.

**Parameters**:
- `story_id` (string, required): ID of the story to read
- `start_chapter` (string, optional): Chapter to start reading from
- `format` (string, optional): Display format (compact, detailed, markdown)
- `include_metadata` (boolean, optional, default: true): Include story metadata

**Usage Examples**:
```
/story_read story_id:"story_12345" format:"detailed" include_metadata:true
/story_read story_id:"story_12345" start_chapter:"Chapter 3" format:"compact"
```

**Required Permissions**: None (if collaborative or public)

### `/story_list`
Shows user's stories with filtering and sorting options.

**Parameters**:
- `filter` (string, optional): Filter by genre, status, or template
- `sort_by` (string, optional): Sort method (title, created, updated, word_count)
- `limit` (int, optional, default: 10): Number of stories to display (1-50)

**Usage Examples**:
```
/story_list filter:"genre:fantasy" sort_by:"updated" limit:15
/story_list filter:"status:collaborative" sort_by:"word_count"
/story_list sort_by:"created" limit:20
```

**Required Permissions**: None (user's own stories)

### `/story_edit`
Edits existing story metadata or content.

**Parameters**:
- `story_id` (string, required): ID of the story to edit
- `field` (string, required): Field to edit (title, description, genre, template, visibility)
- `new_value` (string, required): New value for the field

**Usage Examples**:
```
/story_edit story_id:"story_12345" field:"title" new_value:"The Lost Kingdom: Reborn"
/story_edit story_id:"story_12345" field:"genre" new_value:"fantasy"
/story_edit story_id:"story_12345" field:"visibility" new_value:"public"
```

**Required Permissions**: None (story owner only)

### `/story_delete`
Removes a story (with confirmation).

**Parameters**:
- `story_id` (string, required): ID of the story to delete
- `confirm` (boolean, required): Confirmation flag (must be true)

**Usage Examples**:
```
/story_delete story_id:"story_12345" confirm:true
```

**Required Permissions**: None (story owner only)

### `/story_characters`
Manages story characters and their details.

**Subcommands**:
- `add`: Add a new character
- `edit`: Edit character details
- `list`: List story characters
- `remove`: Remove a character

**Parameters**:
- `action` (string, required): Action to perform (add, edit, list, remove)
- `story_id` (string, required): Story ID
- `character_name` (string, optional): Character name
- `character_details` (string, optional): Character description/details

**Usage Examples**:
```
/story_characters action:"add" story_id:"story_12345" character_name:"Arin the Mage" character_details:"A powerful wizard with a mysterious past"
/story_characters action:"list" story_id:"story_12345"
/story_characters action:"edit" story_id:"story_12345" character_name:"Arin the Mage" character_details:"Now revealed to be the lost prince"
```

**Required Permissions**: None (story owner or collaborative contributor)

### `/story_export`
Exports story in various formats.

**Parameters**:
- `story_id` (string, required): Story ID to export
- `format` (string, optional): Export format (txt, pdf, epub, html, markdown)
- `include_characters` (boolean, optional, default: true): Include character profiles
- `include_metadata` (boolean, optional, default: true): Include story metadata

**Usage Examples**:
```
/story_export story_id:"story_12345" format:"pdf" include_metadata:true
/story_export story_id:"story_12345" format:"epub" include_characters:true
/story_export story_id:"story_12345" format:"markdown" include_metadata:false
```

**Required Permissions**: None (story owner or collaborative contributor)

## Technical Implementation

### Class Structure
```python
class StoryManager(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    
    # Command handlers
    async def story_create_command(self, interaction: discord.Interaction,
                                  title: str, genre: str = "fantasy", template: str = "freeform",
                                  description: str = None, is_collaborative: bool = False)
    
    async def story_write_command(self, interaction: discord.Interaction,
                                 story_id: str, content: str, chapter: str = None,
                                 scene: str = None, perspective: str = "third")
    
    async def story_read_command(self, interaction: discord.Interaction,
                                story_id: str, start_chapter: str = None,
                                format: str = "detailed", include_metadata: bool = True)
    
    async def story_list_command(self, interaction: discord.Interaction,
                                filter: str = None, sort_by: str = "updated", limit: int = 10)
    
    async def story_edit_command(self, interaction: discord.Interaction,
                                story_id: str, field: str, new_value: str)
    
    async def story_delete_command(self, interaction: discord.Interaction,
                                  story_id: str, confirm: bool)
    
    async def story_characters_command(self, interaction: discord.Interaction,
                                      action: str, story_id: str, character_name: str = None,
                                      character_details: str = None)
    
    async def story_export_command(self, interaction: discord.Interaction,
                                  story_id: str, format: str = "txt",
                                  include_characters: bool = True, include_metadata: bool = True)
    
    # Core functionality
    async def create_story(self, user_id: str, story_data: dict) -> str
    async def write_to_story(self, story_id: str, user_id: str, content: str, metadata: dict) -> bool
    async def get_story(self, story_id: str, user_id: str) -> Optional[Story]
    async def get_user_stories(self, user_id: str, filters: dict = None) -> List[Story]
    async def update_story(self, story_id: str, user_id: str, updates: dict) -> bool
    async def delete_story(self, story_id: str, user_id: str) -> bool
```

### Story Data Models
```python
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
import uuid

class StoryGenre(Enum):
    FANTASY = "fantasy"
    SCI_FI = "sci-fi"
    MYSTERY = "mystery"
    ROMANCE = "romance"
    ADVENTURE = "adventure"
    HORROR = "horror"
    SLICE_OF_LIFE = "slice-of-life"
    THRILLER = "thriller"
    HISTORICAL = "historical"
    URBAN_FANTASY = "urban-fantasy"

class StoryTemplate(Enum):
    FREEFORM = "freeform"
    CHAPTER_BASED = "chapter-based"
    EPISODIC = "episodic"
    COLLABORATIVE = "collaborative"
    ROLEPLAYING = "roleplaying"

class NarrativePerspective(Enum):
    FIRST = "first"
    SECOND = "second"
    THIRD = "third"
    OMNISCIENT = "omniscient"
    MULTIPLE = "multiple"

class StoryStatus(Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    ON_HOLD = "on-hold"
    ARCHIVED = "archived"

@dataclass
class StoryCharacter:
    id: str
    story_id: str
    name: str
    description: str
    role: str  # protagonist, antagonist, supporting, minor
    traits: List[str]
    backstory: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'story_id': self.story_id,
            'name': self.name,
            'description': self.description,
            'role': self.role,
            'traits': self.traits,
            'backstory': self.backstory,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

@dataclass
class StoryChapter:
    id: str
    story_id: str
    title: str
    content: str
    word_count: int
    perspective: NarrativePerspective
    created_by: str
    created_at: datetime
    updated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'story_id': self.story_id,
            'title': self.title,
            'content': self.content,
            'word_count': self.word_count,
            'perspective': self.perspective.value,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

@dataclass
class Story:
    id: str
    title: str
    description: str
    genre: StoryGenre
    template: StoryTemplate
    status: StoryStatus
    visibility: str  # private, public, collaborative
    creator_id: str
    
    # Content
    total_word_count: int
    chapter_count: int
    chapters: List[StoryChapter]
    characters: List[StoryCharacter]
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    last_contribution: Optional[datetime]
    
    # Collaborative features
    is_collaborative: bool
    collaborators: List[str]  # User IDs
    contribution_count: Dict[str, int]  # user_id -> word_count contribution
    
    # Settings
    auto_save: bool = True
    ai_assistance: bool = False
    version_control: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'genre': self.genre.value,
            'template': self.template.value,
            'status': self.status.value,
            'visibility': self.visibility,
            'creator_id': self.creator_id,
            'total_word_count': self.total_word_count,
            'chapter_count': self.chapter_count,
            'chapters': [chapter.to_dict() for chapter in self.chapters],
            'characters': [character.to_dict() for character in self.characters],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'last_contribution': self.last_contribution.isoformat() if self.last_contribution else None,
            'is_collaborative': self.is_collaborative,
            'collaborators': self.collaborators,
            'contribution_count': self.contribution_count,
            'auto_save': self.auto_save,
            'ai_assistance': self.ai_assistance,
            'version_control': self.version_control
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Story':
        chapters = [StoryChapter.from_dict(chapter_data) for chapter_data in data.get('chapters', [])]
        characters = [StoryCharacter.from_dict(char_data) for char_data in data.get('characters', [])]
        
        return cls(
            id=data['id'],
            title=data['title'],
            description=data.get('description', ''),
            genre=StoryGenre(data['genre']),
            template=StoryTemplate(data['template']),
            status=StoryStatus(data['status']),
            visibility=data.get('visibility', 'private'),
            creator_id=data['creator_id'],
            total_word_count=data.get('total_word_count', 0),
            chapter_count=data.get('chapter_count', 0),
            chapters=chapters,
            characters=characters,
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            last_contribution=datetime.fromisoformat(data['last_contribution']) if data.get('last_contribution') else None,
            is_collaborative=data.get('is_collaborative', False),
            collaborators=data.get('collaborators', []),
            contribution_count=data.get('contribution_count', {}),
            auto_save=data.get('auto_save', True),
            ai_assistance=data.get('ai_assistance', False),
            version_control=data.get('version_control', True)
        )
    
    def add_chapter(self, chapter: StoryChapter):
        """Add a chapter to the story"""
        self.chapters.append(chapter)
        self.chapter_count = len(self.chapters)
        self.total_word_count += chapter.word_count
        self.updated_at = datetime.now()
        self.last_contribution = datetime.now()
    
    def add_character(self, character: StoryCharacter):
        """Add a character to the story"""
        self.characters.append(character)
        self.updated_at = datetime.now()
    
    def update_contribution_count(self, user_id: str, word_count: int):
        """Update contribution statistics"""
        if user_id not in self.contribution_count:
            self.contribution_count[user_id] = 0
        self.contribution_count[user_id] += word_count
        self.last_contribution = datetime.now()
        self.updated_at = datetime.now()
    
    def calculate_reading_time(self) -> int:
        """Calculate estimated reading time in minutes (assuming 200 words per minute)"""
        return max(1, self.total_word_count // 200)
```

### Story Database Management
```python
import sqlite3
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

class StoryDatabase:
    def __init__(self, db_path: str = "data/story_manager.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize story database"""
        with sqlite3.connect(self.db_path) as conn:
            # Stories table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stories (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    genre TEXT NOT NULL,
                    template TEXT NOT NULL,
                    status TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    creator_id TEXT NOT NULL,
                    total_word_count INTEGER DEFAULT 0,
                    chapter_count INTEGER DEFAULT 0,
                    is_collaborative BOOLEAN DEFAULT FALSE,
                    collaborators TEXT,  -- JSON array
                    contribution_count TEXT,  -- JSON object
                    auto_save BOOLEAN DEFAULT TRUE,
                    ai_assistance BOOLEAN DEFAULT FALSE,
                    version_control BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_contribution DATETIME,
                    FOREIGN KEY (creator_id) REFERENCES users(id)
                )
            """)
            
            # Chapters table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS story_chapters (
                    id TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    perspective TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    chapter_order INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (story_id) REFERENCES stories(id),
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            """)
            
            # Characters table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS story_characters (
                    id TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    role TEXT NOT NULL,
                    traits TEXT,  -- JSON array
                    backstory TEXT,
                    created_by TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (story_id) REFERENCES stories(id),
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            """)
            
            # Story collaborations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS story_collaborations (
                    story_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    permission_level TEXT NOT NULL,  -- read, write, admin
                    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (story_id, user_id),
                    FOREIGN KEY (story_id) REFERENCES stories(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            # Indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_creator ON stories (creator_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_genre ON stories (genre)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_status ON stories (status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chapters_story ON story_chapters (story_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_characters_story ON story_characters (story_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_collaborations_story ON story_collaborations (story_id)")
    
    def create_story(self, story: Story) -> bool:
        """Create a new story in the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO stories 
                    (id, title, description, genre, template, status, visibility, creator_id,
                     total_word_count, chapter_count, is_collaborative, collaborators, contribution_count,
                     auto_save, ai_assistance, version_control)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    story.id,
                    story.title,
                    story.description,
                    story.genre.value,
                    story.template.value,
                    story.status.value,
                    story.visibility,
                    story.creator_id,
                    story.total_word_count,
                    story.chapter_count,
                    story.is_collaborative,
                    json.dumps(story.collaborators) if story.collaborators else None,
                    json.dumps(story.contribution_count) if story.contribution_count else None,
                    story.auto_save,
                    story.ai_assistance,
                    story.version_control
                ))
                
                return True
                
        except Exception as e:
            await func.report_error(e, "create_story")
            return False
    
    def get_story(self, story_id: str) -> Optional[Story]:
        """Get a story by ID with all related data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Get story data
                story_cursor = conn.execute("""
                    SELECT * FROM stories WHERE id = ?
                """, (story_id,))
                
                story_row = story_cursor.fetchone()
                if not story_row:
                    return None
                
                # Get chapters
                chapters_cursor = conn.execute("""
                    SELECT * FROM story_chapters WHERE story_id = ? ORDER BY chapter_order ASC, created_at ASC
                """, (story_id,))
                
                chapters = []
                for row in chapters_cursor:
                    chapter_data = dict(row)
                    chapters.append(StoryChapter.from_dict(chapter_data))
                
                # Get characters
                characters_cursor = conn.execute("""
                    SELECT * FROM story_characters WHERE story_id = ?
                """, (story_id,))
                
                characters = []
                for row in characters_cursor:
                    char_data = dict(row)
                    characters.append(StoryCharacter.from_dict(char_data))
                
                # Parse JSON fields
                story_data = dict(story_row)
                story_data['chapters'] = [chapter.to_dict() for chapter in chapters]
                story_data['characters'] = [character.to_dict() for character in characters]
                
                if story_data['collaborators']:
                    story_data['collaborators'] = json.loads(story_data['collaborators'])
                else:
                    story_data['collaborators'] = []
                
                if story_data['contribution_count']:
                    story_data['contribution_count'] = json.loads(story_data['contribution_count'])
                else:
                    story_data['contribution_count'] = {}
                
                return Story.from_dict(story_data)
                
        except Exception as e:
            await func.report_error(e, "get_story")
            return None
    
    def get_user_stories(self, user_id: str, filters: Dict[str, Any] = None) -> List[Story]:
        """Get all stories for a user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Build query for stories user created or collaborates on
                query = """
                    SELECT DISTINCT s.* FROM stories s
                    LEFT JOIN story_collaborations sc ON s.id = sc.story_id
                    WHERE s.creator_id = ? OR sc.user_id = ?
                """
                params = [user_id, user_id]
                
                # Add filters
                if filters:
                    if 'genre' in filters and filters['genre']:
                        query += " AND s.genre = ?"
                        params.append(filters['genre'])
                    
                    if 'status' in filters and filters['status']:
                        query += " AND s.status = ?"
                        params.append(filters['status'])
                    
                    if 'template' in filters and filters['template']:
                        query += " AND s.template = ?"
                        params.append(filters['template'])
                    
                    if 'visibility' in filters and filters['visibility']:
                        query += " AND s.visibility = ?"
                        params.append(filters['visibility'])
                    
                    # Add sorting
                    if 'sort_by' in filters:
                        sort_field = self._get_sort_field(filters['sort_by'])
                        sort_order = "DESC" if filters.get('sort_order', 'desc') == 'desc' else "ASC"
                        query += f" ORDER BY s.{sort_field} {sort_order}"
                    else:
                        query += " ORDER BY s.updated_at DESC"
                    
                    # Add limit
                    if 'limit' in filters:
                        query += " LIMIT ?"
                        params.append(filters['limit'])
                    else:
                        query += " LIMIT 50"
                else:
                    query += " ORDER BY s.updated_at DESC LIMIT 50"
                
                cursor = conn.execute(query, params)
                
                stories = []
                for row in cursor:
                    story_data = dict(row)
                    
                    # Parse JSON fields
                    if story_data['collaborators']:
                        story_data['collaborators'] = json.loads(story_data['collaborators'])
                    else:
                        story_data['collaborators'] = []
                    
                    if story_data['contribution_count']:
                        story_data['contribution_count'] = json.loads(story_data['contribution_count'])
                    else:
                        story_data['contribution_count'] = {}
                    
                    # Get chapters count
                    chapters_count = conn.execute("""
                        SELECT COUNT(*) as count FROM story_chapters WHERE story_id = ?
                    """, (story_data['id'],)).fetchone()['count']
                    
                    story_data['chapter_count'] = chapters_count
                    story_data['chapters'] = []
                    story_data['characters'] = []
                    
                    stories.append(Story.from_dict(story_data))
                
                return stories
                
        except Exception as e:
            await func.report_error(e, "get_user_stories")
            return []
    
    def add_chapter(self, chapter: StoryChapter) -> bool:
        """Add a chapter to a story"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO story_chapters 
                    (id, story_id, title, content, word_count, perspective, created_by, chapter_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chapter.id,
                    chapter.story_id,
                    chapter.title,
                    chapter.content,
                    chapter.word_count,
                    chapter.perspective.value,
                    chapter.created_by,
                    getattr(chapter, 'chapter_order', None)
                ))
                
                # Update story statistics
                conn.execute("""
                    UPDATE stories 
                    SET total_word_count = total_word_count + ?, 
                        chapter_count = chapter_count + 1,
                        updated_at = CURRENT_TIMESTAMP,
                        last_contribution = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (chapter.word_count, chapter.story_id))
                
                return True
                
        except Exception as e:
            await func.report_error(e, "add_chapter")
            return False
    
    def add_character(self, character: StoryCharacter) -> bool:
        """Add a character to a story"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO story_characters 
                    (id, story_id, name, description, role, traits, backstory, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    character.id,
                    character.story_id,
                    character.name,
                    character.description,
                    character.role,
                    json.dumps(character.traits) if character.traits else None,
                    character.backstory,
                    character.created_by
                ))
                
                # Update story updated timestamp
                conn.execute("""
                    UPDATE stories 
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (character.story_id,))
                
                return True
                
        except Exception as e:
            await func.report_error(e, "add_character")
            return False
    
    def update_story(self, story_id: str, updates: Dict[str, Any]) -> bool:
        """Update story metadata"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Build update query
                set_clauses = []
                params = []
                
                for field, value in updates.items():
                    if field == 'genre':
                        set_clauses.append("genre = ?")
                        params.append(value.value if hasattr(value, 'value') else value)
                    elif field == 'template':
                        set_clauses.append("template = ?")
                        params.append(value.value if hasattr(value, 'value') else value)
                    elif field == 'status':
                        set_clauses.append("status = ?")
                        params.append(value.value if hasattr(value, 'value') else value)
                    elif field in ['title', 'description', 'visibility']:
                        set_clauses.append(f"{field} = ?")
                        params.append(value)
                    elif field in ['is_collaborative', 'auto_save', 'ai_assistance', 'version_control']:
                        set_clauses.append(f"{field} = ?")
                        params.append(bool(value))
                    elif field == 'collaborators':
                        set_clauses.append("collaborators = ?")
                        params.append(json.dumps(value) if value else None)
                    elif field == 'contribution_count':
                        set_clauses.append("contribution_count = ?")
                        params.append(json.dumps(value) if value else None)
                    else:
                        set_clauses.append(f"{field} = ?")
                        params.append(value)
                
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                params.append(story_id)
                
                query = f"""
                    UPDATE stories 
                    SET {', '.join(set_clauses)}
                    WHERE id = ?
                """
                
                conn.execute(query, params)
                return True
                
        except Exception as e:
            await func.report_error(e, "update_story")
            return False
    
    def delete_story(self, story_id: str) -> bool:
        """Delete a story and all related data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Delete in correct order due to foreign key constraints
                conn.execute("DELETE FROM story_chapters WHERE story_id = ?", (story_id,))
                conn.execute("DELETE FROM story_characters WHERE story_id = ?", (story_id,))
                conn.execute("DELETE FROM story_collaborations WHERE story_id = ?", (story_id,))
                conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
                
                return True
                
        except Exception as e:
            await func.report_error(e, "delete_story")
            return False
    
    def _get_sort_field(self, sort_by: str) -> str:
        """Get database field name for sorting"""
        
        sort_mapping = {
            'title': 'title',
            'created': 'created_at',
            'updated': 'updated_at',
            'word_count': 'total_word_count',
            'chapter_count': 'chapter_count'
        }
        
        return sort_mapping.get(sort_by, 'updated_at')
```

### AI Story Generation Engine
```python
import random
from typing import List, Dict, Any, Optional

class AIStoryGenerator:
    def __init__(self):
        self.genre_templates = {
            StoryGenre.FANTASY: {
                'settings': ['medieval kingdom', 'enchanted forest', 'magical academy', 'ancient ruins', 'floating islands'],
                'characters': ['wizard', 'knight', 'princess', 'dragon', 'elf', 'dwarf', 'sorceress'],
                'conflicts': ['prophecy', 'ancient evil', 'missing artifact', 'forbidden magic', 'rival kingdoms'],
                'themes': ['good vs evil', 'coming of age', 'friendship', 'power and responsibility', 'redemption']
            },
            StoryGenre.SCI_FI: {
                'settings': ['space station', 'alien planet', 'cyberpunk city', 'post-apocalyptic Earth', 'generation ship'],
                'characters': ['astronaut', 'android', 'alien', 'scientist', 'pilot', 'hacker', 'explorer'],
                'conflicts': ['first contact', 'technology gone wrong', 'space exploration', 'genetic engineering', 'AI uprising'],
                'themes': ['humanity vs technology', 'exploration', 'survival', 'identity', 'progress vs tradition']
            },
            StoryGenre.MYSTERY: {
                'settings': ['small town', 'vintage mansion', 'police station', 'haunted house', 'luxury hotel'],
                'characters': ['detective', 'victim', 'suspect', 'witness', 'butler', 'heir', 'journalist'],
                'conflicts': ['murder', 'missing person', 'stolen artifact', 'conspiracy', 'identity theft'],
                'themes': ['justice vs injustice', 'truth vs deception', 'past catching up', 'moral ambiguity', 'redemption']
            }
        }
        
        self.writing_prompts = {
            'opening': [
                "The {setting} was never the same after {event}.",
                "When {character} discovered {discovery}, they knew their life would change forever.",
                "It all started with a {object} and a single {action}.",
                "The first rule of {location} was simple: never {taboo}.",
                "On the day {character} turned {age}, the world ended."
            ],
            'character_introduction': [
                "Meet {name}, a {adjective} {profession} with a {trait} that makes them {unique}.",
                "{name} had always been different, but it wasn't until {situation} that they realized how much.",
                "Nobody expected {name} to be the {role}, especially not {name} themselves."
            ],
            'plot_development': [
                "Everything changed when {event} forced {character} to {action}.",
                "The truth about {mystery} was more complicated than anyone had imagined.",
                "As tensions rose, {character} realized they had to choose between {option1} and {option2}."
            ]
        }

    async def generate_story_seed(self, genre: StoryGenre, user_preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        """Generate a story seed with characters, setting, and plot"""
        
        template = self.genre_templates.get(genre, self.genre_templates[StoryGenre.FANTASY])
        
        # Select random elements
        setting = random.choice(template['settings'])
        character = random.choice(template['characters'])
        conflict = random.choice(template['conflicts'])
        theme = random.choice(template['themes'])
        
        # Generate character details
        adjectives = ['brave', 'mysterious', 'clever', 'reckless', 'wise', 'cunning', 'kind']
        character_name = self._generate_character_name()
        character_adjective = random.choice(adjectives)
        
        # Create story seed
        seed = {
            'title': self._generate_title(genre, character, setting),
            'setting': setting,
            'protagonist': {
                'name': character_name,
                'type': character,
                'adjective': character_adjective,
                'role': 'protagonist'
            },
            'central_conflict': conflict,
            'main_theme': theme,
            'genre': genre.value,
            'estimated_length': self._estimate_length(genre),
            'potential_chapters': self._generate_chapter_outline(genre, conflict)
        }
        
        # Add user preferences if provided
        if user_preferences:
            seed.update(user_preferences)
        
        return seed
    
    async def generate_chapter_content(self, story: Story, chapter_context: Dict[str, Any], user_input: str = None) -> str:
        """Generate AI-assisted chapter content"""
        
        if not story.ai_assistance:
            return user_input or "AI assistance is not enabled for this story."
        
        # Build context for AI generation
        context = f"""
        Story Title: {story.title}
        Genre: {story.genre.value}
        Current Chapter: {chapter_context.get('title', 'New Chapter')}
        Previous Chapter Summary: {chapter_context.get('previous_summary', 'No previous content')}
        User Input: {user_input or 'No specific input provided'}
        
        Please write a compelling chapter that:
        1. Follows the story's established tone and style
        2. Develops the plot naturally
        3. Maintains character consistency
        4. Is approximately 500-1000 words
        5. Ends with a hook for the next chapter
        """
        
        # This would integrate with an AI service like OpenAI, Claude, or local LLM
        # For now, return a placeholder
        generated_content = f"""
        **AI Generated Chapter Content**
        
        This is where the AI would generate chapter content based on:
        - Story context: {story.description}
        - Genre: {story.genre.value}
        - User input: {user_input or 'None provided'}
        
        The AI would create approximately 500-1000 words of compelling narrative content.
        [Content generation would happen here using AI services]
        """
        
        return generated_content.strip()
    
    def _generate_character_name(self) -> str:
        """Generate a random character name"""
        
        first_names = [
            'Alex', 'Sam', 'Jordan', 'Taylor', 'Morgan', 'Casey', 'Riley', 'Avery',
            'Rowan', 'Quinn', 'Sage', 'Phoenix', 'River', 'Sky', 'Ocean', 'Luna',
            'Arin', 'Kael', 'Zara', 'Nova', 'Orion', 'Luca', 'Iris', 'Eden'
        ]
        
        last_names = [
            'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
            'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson',
            'Thornfield', 'Blackwood', 'Silvermoon', 'Stormwind', 'Quickblade', 'Starweaver'
        ]
        
        return f"{random.choice(first_names)} {random.choice(last_names)}"
    
    def _generate_title(self, genre: StoryGenre, character: str, setting: str) -> str:
        """Generate a story title based on genre elements"""
        
        titles = {
            StoryGenre.FANTASY: [
                f"The Chronicles of {character.title()}",
                f"Legends of {setting.title()}",
                f"The {character.title()}'s Quest",
                f"Mysteries of {setting.title()}",
                f"The {setting.title()} Chronicles"
            ],
            StoryGenre.SCI_FI: [
                f"Beyond {setting.title()}",
                f"The {character.title()} Protocol",
                f"Echoes from {setting.title()}",
                f"Frontiers of {setting.title()}",
                f"The {character.title()} Files"
            ],
            StoryGenre.MYSTERY: [
                f"The Case of {setting.title()}",
                f"Secrets of {setting.title()}",
                f"The {character.title()} Mystery",
                f"Whispers in {setting.title()}",
                f"The {setting.title()} Enigma"
            ]
        }
        
        genre_titles = titles.get(genre, titles[StoryGenre.FANTASY])
        return random.choice(genre_titles)
    
    def _estimate_length(self, genre: StoryGenre) -> str:
        """Estimate story length based on genre"""
        
        length_estimates = {
            StoryGenre.FANTASY: "8-15 chapters",
            StoryGenre.SCI_FI: "6-12 chapters", 
            StoryGenre.MYSTERY: "4-8 chapters",
            StoryGenre.ROMANCE: "5-10 chapters",
            StoryGenre.HORROR: "3-7 chapters"
        }
        
        return length_estimates.get(genre, "5-10 chapters")
    
    def _generate_chapter_outline(self, genre: StoryGenre, conflict: str) -> List[str]:
        """Generate a basic chapter outline"""
        
        outlines = {
            StoryGenre.FANTASY: [
                "Chapter 1: The Call to Adventure",
                "Chapter 2: Meeting the Mentor",
                "Chapter 3: First Trial",
                "Chapter 4: The Journey Begins",
                "Chapter 5: Major Conflict",
                "Chapter 6: Dark Moment",
                "Chapter 7: Resolution"
            ],
            StoryGenre.SCI_FI: [
                "Chapter 1: Discovery",
                "Chapter 2: Investigation", 
                "Chapter 3: First Contact",
                "Chapter 4: Conflict Arises",
                "Chapter 5: Crisis Point",
                "Chapter 6: Resolution"
            ],
            StoryGenre.MYSTERY: [
                "Chapter 1: The Crime",
                "Chapter 2: Investigation Begins",
                "Chapter 3: First Clues",
                "Chapter 4: Suspects Emerge",
                "Chapter 5: The Revelation",
                "Chapter 6: Justice Served"
            ]
        }
        
        return outlines.get(genre, outlines[StoryGenre.FANTASY])
```

### Collaborative Writing System
```python
from typing import Set, Dict, Any
import asyncio
from datetime import datetime

class CollaborativeEditor:
    def __init__(self, story_db: StoryDatabase):
        self.db = story_db
        self.active_sessions = {}  # story_id -> session data
        self.lock = asyncio.Lock()
    
    async def join_story_session(self, story_id: str, user_id: str, permission: str = "write") -> bool:
        """Add user to collaborative story session"""
        
        async with self.lock:
            if story_id not in self.active_sessions:
                self.active_sessions[story_id] = {
                    'users': {},
                    'current_section': None,
                    'edit_queue': [],
                    'last_activity': datetime.now()
                }
            
            session = self.active_sessions[story_id]
            session['users'][user_id] = {
                'permission': permission,
                'joined_at': datetime.now(),
                'last_activity': datetime.now()
            }
            session['last_activity'] = datetime.now()
            
            return True
    
    async def leave_story_session(self, story_id: str, user_id: str) -> bool:
        """Remove user from collaborative story session"""
        
        async with self.lock:
            if story_id in self.active_sessions:
                session = self.active_sessions[story_id]
                if user_id in session['users']:
                    del session['users'][user_id]
                    
                    # Clean up empty sessions
                    if not session['users']:
                        del self.active_sessions[story_id]
                
                return True
            
            return False
    
    async def submit_edits(self, story_id: str, user_id: str, edits: List[Dict[str, Any]]) -> bool:
        """Submit edits for collaborative processing"""
        
        async with self.lock:
            if story_id not in self.active_sessions:
                return False
            
            session = self.active_sessions[story_id]
            
            # Add edits to queue
            for edit in edits:
                edit['user_id'] = user_id
                edit['timestamp'] = datetime.now()
                session['edit_queue'].append(edit)
            
            # Update user activity
            if user_id in session['users']:
                session['users'][user_id]['last_activity'] = datetime.now()
            
            session['last_activity'] = datetime.now()
            
            return True
    
    async def get_session_status(self, story_id: str) -> Dict[str, Any]:
        """Get current collaborative session status"""
        
        async with self.lock:
            if story_id not in self.active_sessions:
                return {'active': False, 'users': []}
            
            session = self.active_sessions[story_id]
            
            return {
                'active': True,
                'users': [
                    {
                        'user_id': user_id,
                        'permission': user_data['permission'],
                        'joined_at': user_data['joined_at'].isoformat(),
                        'last_activity': user_data['last_activity'].isoformat()
                    }
                    for user_id, user_data in session['users'].items()
                ],
                'edit_queue_size': len(session['edit_queue']),
                'last_activity': session['last_activity'].isoformat()
            }
    
    async def process_edit_queue(self, story_id: str) -> List[Dict[str, Any]]:
        """Process pending edits and return merged changes"""
        
        async with self.lock:
            if story_id not in self.active_sessions:
                return []
            
            session = self.active_sessions[story_id]
            
            if not session['edit_queue']:
                return []
            
            # Process edits (simplified version)
            processed_edits = session['edit_queue'].copy()
            session['edit_queue'] = []
            
            return processed_edits
    
    async def cleanup_inactive_sessions(self, timeout_minutes: int = 30):
        """Clean up inactive collaborative sessions"""
        
        async with self.lock:
            cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)
            
            inactive_sessions = [
                story_id for story_id, session in self.active_sessions.items()
                if session['last_activity'] < cutoff_time
            ]
            
            for story_id in inactive_sessions:
                del self.active_sessions[story_id]
            
            return len(inactive_sessions)
```

## Error Handling

### Story Error Management
```python
async def handle_story_error(self, interaction, error, context: str, story_id: str = None):
    """Handle story-related errors with user-friendly messages"""
    
    error_messages = {
        "story_not_found": f"Story not found or you don't have permission to access it.",
        "permission_denied": "You don't have permission to edit this story.",
        "content_too_long": "Story content is too long. Please keep chapters under 5000 characters.",
        "title_taken": "A story with this title already exists. Please choose a different title.",
        "collaboration_failed": "Unable to add collaborator. They may have reached their collaboration limit.",
        "invalid_genre": "Invalid story genre specified.",
        "rate_limit_exceeded": "Story operation rate limit exceeded. Please wait before trying again.",
        "database_error": "Database error occurred. Please try again later.",
        "export_failed": "Story export failed. Please try again with different parameters.",
        "ai_service_unavailable": "AI story generation service is temporarily unavailable."
    }
    
    # Determine error type and provide appropriate message
    error_str = str(error).lower()
    
    if "not found" in error_str or "no such" in error_str:
        message = error_messages["story_not_found"]
    elif "permission" in error_str or "denied" in error_str:
        message = error_messages["permission_denied"]
    elif "too long" in error_str or "content" in error_str:
        message = error_messages["content_too_long"]
    elif "title" in error_str and "taken" in error_str:
        message = error_messages["title_taken"]
    elif "collaboration" in error_str or "collaborator" in error_str:
        message = error_messages["collaboration_failed"]
    elif "genre" in error_str:
        message = error_messages["invalid_genre"]
    elif "rate limit" in error_str or "quota" in error_str:
        message = error_messages["rate_limit_exceeded"]
    elif "export" in error_str:
        message = error_messages["export_failed"]
    elif "ai" in error_str or "service" in error_str:
        message = error_messages["ai_service_unavailable"]
    else:
        message = error_messages["database_error"]
    
    await interaction.response.send_message(message, ephemeral=True)
    await func.report_error(error, f"story_{context}_{story_id or 'unknown'}")
```

## Usage Examples

### Creating and Writing Stories
```
User: /story_create title:"The Lost Kingdom" genre:"fantasy" template:"chapter-based" description:"An epic tale of discovery"
Bot: ✅ Story created successfully!
Story ID: story_12345
Title: The Lost Kingdom
Genre: Fantasy
Template: Chapter-based
Status: Draft

AI Story Seed Generated:
• Setting: Medieval Kingdom
• Protagonist: Arin Thornfield (mysterious wizard)
• Central Conflict: Ancient Evil awakening
• Theme: Good vs Evil
• Estimated Length: 8-15 chapters

Use /story_write to start adding content!

User: /story_write story_id:"story_12345" content:"The old castle loomed in the distance as Arin approached the forbidden kingdom..." chapter:"Chapter 1: The Journey Begins" scene:"Arrival"
Bot: ✅ Chapter added successfully!
Chapter: Chapter 1: The Journey Begins
Word Count: 47 words
Total Story: 47 words
Last Updated: Just now

Ready to continue the adventure!
```

### Story Management and Collaboration
```
User: /story_characters action:"add" story_id:"story_12345" character_name:"Luna Starweaver" character_details:"A wise elf sorceress who guides Arin on his quest"
Bot: ✅ Character added successfully!
Character: Luna Starweaver
Role: Mentor/Guide
Traits: Wise, Mysterious, Compassionate
Story: The Lost Kingdom

User: /story_list filter:"genre:fantasy" sort_by:"word_count" limit:5
Bot: ## Your Fantasy Stories

1. **The Lost Kingdom** (story_12345) - Draft
   📊 2 chapters, 1,247 words, 1 character
   📅 Created: 2 hours ago | Updated: 30 minutes ago
   
2. **Dragon's Legacy** (story_12344) - In Progress  
   📊 5 chapters, 3,891 words, 4 characters
   📅 Created: 1 week ago | Updated: 3 days ago

Total: 2 fantasy stories, 5,138 words

User: /story_edit story_id:"story_12345" field:"visibility" new_value:"collaborative"
Bot: ✅ Story updated successfully!
The Lost Kingdom is now open for collaboration.

Use /story_invite to add collaborators.
```

### Story Reading and Export
```
User: /story_read story_id:"story_12345" format:"detailed" include_metadata:true
Bot: # The Lost Kingdom
*A Fantasy Epic*

## Story Information
- **Genre**: Fantasy
- **Template**: Chapter-based
- **Status**: Draft
- **Total Words**: 1,247
- **Chapters**: 2
- **Characters**: 1
- **Created**: December 20, 2024
- **Last Updated**: December 20, 2024

## Characters
### Luna Starweaver
*Mentor/Guide*
A wise elf sorceress who guides Arin on his quest

---

## Chapter 1: The Journey Begins
*The morning mist clung to the ancient stones as Arin approached the kingdom's border...*

[Full chapter content would be displayed here with proper formatting]

## Chapter 2: First Encounter  
*Chapter content would continue...*

---

User: /story_export story_id:"story_12345" format:"pdf" include_characters:true include_metadata:true
Bot: 📤 Story Export Complete!

Your story "The Lost Kingdom" has been exported as a PDF file containing:
• Complete story text (2 chapters, 1,247 words)
• Character profiles (1 character)
• Story metadata and statistics
• Professional formatting

File ready for download (2.3 MB)
```

## Advanced Features

### Story Analytics
```python
class StoryAnalytics:
    def __init__(self, story_db: StoryDatabase):
        self.db = story_db
    
    def generate_story_insights(self, story: Story) -> Dict[str, Any]:
        """Generate insights and analytics for a story"""
        
        insights = {
            'basic_stats': {
                'word_count': story.total_word_count,
                'chapter_count': story.chapter_count,
                'character_count': len(story.characters),
                'reading_time_minutes': story.calculate_reading_time(),
                'collaboration_level': len(story.collaborators) if story.is_collaborative else 0
            },
            'writing_pace': self._analyze_writing_pace(story),
            'character_development': self._analyze_character_development(story),
            'engagement_metrics': self._calculate_engagement_metrics(story),
            'quality_indicators': self._assess_story_quality(story),
            'recommendations': self._generate_recommendations(story)
        }
        
        return insights
    
    def _analyze_writing_pace(self, story: Story) -> Dict[str, Any]:
        """Analyze writing pace and consistency"""
        
        if not story.chapters:
            return {'pace': 'none', 'consistency': 'unknown'}
        
        # Calculate word count progression
        word_counts = [chapter.word_count for chapter in story.chapters]
        avg_words = sum(word_counts) / len(word_counts)
        
        # Calculate consistency (standard deviation)
        variance = sum((wc - avg_words) ** 2 for wc in word_counts) / len(word_counts)
        consistency_score = 1 - min(variance / (avg_words ** 2), 1)  # Normalize to 0-1
        
        # Determine pace
        if avg_words < 300:
            pace = 'slow'
        elif avg_words > 1000:
            pace = 'fast'
        else:
            pace = 'moderate'
        
        return {
            'pace': pace,
            'average_words_per_chapter': round(avg_words),
            'consistency_score': round(consistency_score * 100, 1),
            'total_sessions': len(story.chapters)
        }
    
    def _analyze_character_development(self, story: Story) -> Dict[str, Any]:
        """Analyze character development and distribution"""
        
        if not story.characters:
            return {'development_level': 'none', 'distribution': 'unbalanced'}
        
        # Character role distribution
        roles = [char.role for char in story.characters]
        role_counts = {role: roles.count(role) for role in set(roles)}
        
        # Development indicators
        main_characters = [char for char in story.characters if char.role in ['protagonist', 'antagonist']]
        supporting_characters = [char for char in story.characters if char.role == 'supporting']
        minor_characters = [char for char in story.characters if char.role == 'minor']
        
        # Calculate development score
        total_chars = len(story.characters)
        development_score = min(len(main_characters) / max(total_chars, 1), 1)
        
        return {
            'development_level': 'good' if development_score > 0.7 else 'moderate' if development_score > 0.4 else 'poor',
            'character_distribution': {
                'main': len(main_characters),
                'supporting': len(supporting_characters),
                'minor': len(minor_characters)
            },
            'total_characters': total_chars
        }
    
    def _calculate_engagement_metrics(self, story: Story) -> Dict[str, Any]:
        """Calculate story engagement metrics"""
        
        # Collaboration metrics
        collaboration_rate = len(story.collaborators) / max(story.total_word_count / 1000, 1)  # Collaborators per 1000 words
        
        # Contribution distribution (if collaborative)
        contribution_distribution = {}
        if story.is_collaborative and story.contribution_count:
            total_contributions = sum(story.contribution_count.values())
            for user_id, contribution in story.contribution_count.items():
                percentage = (contribution / max(total_contributions, 1)) * 100
                contribution_distribution[user_id] = round(percentage, 1)
        
        return {
            'collaboration_rate': round(collaboration_rate, 2),
            'contribution_distribution': contribution_distribution,
            'collaborator_activity': len(story.contributors) if hasattr(story, 'contributors') else 0
        }
    
    def _assess_story_quality(self, story: Story) -> Dict[str, Any]:
        """Assess story quality based on various indicators"""
        
        quality_indicators = []
        
        # Word count adequacy
        if story.total_word_count < 1000:
            quality_indicators.append('short')
        elif story.total_word_count > 10000:
            quality_indicators.append('substantial')
        else:
            quality_indicators.append('adequate')
        
        # Chapter structure
        if story.chapter_count == 0:
            quality_indicators.append('no_structure')
        elif story.chapter_count < 3:
            quality_indicators.append('minimal_structure')
        elif story.chapter_count > 20:
            quality_indicators.append('complex_structure')
        else:
            quality_indicators.append('good_structure')
        
        # Character development
        if len(story.characters) == 0:
            quality_indicators.append('no_characters')
        elif len(story.characters) > 10:
            quality_indicators.append('many_characters')
        else:
            quality_indicators.append('well_populated')
        
        # Genre consistency (would need more sophisticated analysis)
        quality_indicators.append('genre_appropriate')
        
        # Calculate overall quality score
        positive_indicators = len([i for i in quality_indicators if i not in ['short', 'no_structure', 'no_characters']])
        quality_score = (positive_indicators / len(quality_indicators)) * 100
        
        return {
            'quality_score': round(quality_score, 1),
            'indicators': quality_indicators,
            'assessment': 'excellent' if quality_score > 80 else 'good' if quality_score > 60 else 'fair' if quality_score > 40 else 'needs_improvement'
        }
    
    def _generate_recommendations(self, story: Story) -> List[str]:
        """Generate personalized recommendations for story improvement"""
        
        recommendations = []
        
        # Length recommendations
        if story.total_word_count < 1000:
            recommendations.append("Consider expanding your story to at least 1,000 words for better reader engagement.")
        elif story.total_word_count > 10000:
            recommendations.append("Your story is quite substantial! Consider organizing it into a series or editing for conciseness.")
        
        # Structure recommendations
        if story.chapter_count == 0:
            recommendations.append("Add chapter divisions to improve story structure and pacing.")
        elif story.chapter_count == 1 and story.total_word_count > 2000:
            recommendations.append("Consider splitting your long content into multiple chapters for better readability.")
        
        # Character recommendations
        if len(story.characters) == 0:
            recommendations.append("Add characters to make your story more engaging and dynamic.")
        elif len(story.characters) > 10:
            recommendations.append("You have many characters! Consider focusing development on the most important ones.")
        
        # Collaboration recommendations
        if story.is_collaborative and len(story.collaborators) == 0:
            recommendations.append("Your story is marked as collaborative! Invite others to contribute and build upon your work.")
        
        # Genre-specific recommendations
        if story.genre == StoryGenre.FANTASY and len(story.characters) == 0:
            recommendations.append("Fantasy stories benefit from rich character development. Consider adding protagonists, mentors, and conflicts.")
        
        return recommendations
```

## Configuration Options

### Bot Settings
```python
# Configuration in addons/settings.py
STORY_MANAGER_CONFIG = {
    "max_stories_per_user": 50,
    "max_collaborators_per_story": 10,
    "max_chapters_per_story": 100,
    "max_words_per_chapter": 5000,
    "max_characters_per_story": 20,
    "auto_save_interval": 300,  # 5 minutes
    "ai_assistance": {
        "enabled": True,
        "service_provider": "openai",  # openai, claude, local
        "max_tokens_per_request": 1000,
        "temperature": 0.7
    },
    "collaborative_writing": {
        "enabled": True,
        "max_concurrent_sessions": 5,
        "session_timeout": 1800,  # 30 minutes
        "edit_queue_size": 50
    },
    "export_formats": ["txt", "pdf", "epub", "html", "markdown"],
    "supported_genres": ["fantasy", "sci-fi", "mystery", "romance", "adventure", "horror", "slice-of-life"],
    "templates": ["freeform", "chapter-based", "episodic", "collaborative", "roleplaying"]
}
```

## Integration Points

### With Other Cogs
```python
# Integration with user data for preferences
from cogs.userdata import UserData

# Integration with language manager for localization
from cogs.language_manager import LanguageManager

# Integration with memory systems for story context
from cogs.episodic_memory import EpisodicMemory
```

### External Services
- **AI Story Generation**: OpenAI GPT, Anthropic Claude, local LLM models
- **Document Processing**: Libraries for PDF, EPUB export generation
- **Cloud Storage**: AWS S3, Google Cloud Storage for story backups
- **Publishing Platforms**: Integration with Wattpad, Archive of Our Own, etc.

## Related Files

- `cogs/story_manager.py` - Main implementation
- `data/story_manager.db` - SQLite database for stories
- `translations/en_US/commands/story_manager.json` - English translations
- `LanguageManager` - Translation system
- `addons.settings` - Configuration management

## Future Enhancements

Potential improvements:
- **Visual Story Creation**: Integration with image generation for story illustrations
- **Voice Narration**: Text-to-speech for story reading
- **Publishing Integration**: Direct publishing to story platforms
- **Interactive Stories**: Reader choice and branching narratives
- **Story Analytics**: Advanced metrics for story performance
- **Writing Assistant**: Real-time grammar and style suggestions
- **Collaborative World-building**: Shared universe creation
- **Story Versioning**: Git-like version control for stories
- **Reading Community**: Social features for story sharing and feedback
- **Multimedia Stories**: Support for audio, video, and interactive elements
- **AI Co-author**: Advanced AI assistance for plot development and character creation
- **Story Marketplace**: Platform for sharing and discovering stories