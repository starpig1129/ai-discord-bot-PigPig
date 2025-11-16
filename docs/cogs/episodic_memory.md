# EpisodicMemory Cog Documentation

## Overview

The EpisodicMemory cog provides advanced memory management and context retention capabilities for Discord users. It enables users to store, retrieve, and manage personal memories, conversation history, and contextual information across sessions with intelligent search, organization, and recall features.

## Features

### Core Functionality
- **Personal Memory Storage**: Store and retrieve personal memories and experiences
- **Conversation Context**: Maintain context across Discord sessions and channels
- **Intelligent Search**: Search memories by content, tags, date, and relevance
- **Memory Organization**: Categorize memories with tags, importance levels, and relationships
- **Contextual Recall**: Automatic memory retrieval based on conversation context
- **Memory Analytics**: Track memory usage patterns and insights

### Key Components
- `EpisodicMemory` class - Main cog implementation
- Memory storage and retrieval system
- Context analysis and matching engine
- Memory tagging and organization system
- Search and filtering capabilities

## Commands

### `/memory_store`
Stores a new memory with optional context and tags.

**Parameters**:
- `content` (string, required): Memory content to store
- `title` (string, optional): Memory title/summary
- `tags` (string, optional): Comma-separated tags for organization
- `importance` (string, optional): Importance level (low, medium, high, critical)
- `context` (string, optional): Context information (where, when, why)

**Usage Examples**:
```
/memory_store content:"Met Sarah at the coffee shop on Main Street" title:"Meeting Sarah" tags:"coffee,friend,main-street" importance:"medium"
/memory_store content:"Remember to call Dr. Smith about appointment" title:"Doctor Call" tags:"health,appointment" importance:"high"
/memory_store content:"Favorite recipe ingredients" title:"Recipe: Spaghetti Carbonara" tags:"cooking,recipe,pasta" importance:"low"
```

**Required Permissions**: None (personal memories)

### `/memory_search`
Searches stored memories by content, tags, or keywords.

**Parameters**:
- `query` (string, required): Search query or keywords
- `search_type` (string, optional): Type of search (content, tags, title, all)
- `tags` (string, optional): Filter by specific tags
- `date_range` (string, optional): Time range (last_week, last_month, last_year, all)
- `limit` (int, optional, default: 10): Number of results to return (1-50)

**Usage Examples**:
```
/memory_search query:"coffee" search_type:"content" limit:10
/memory_search query:"appointment" tags:"health" date_range:"last_month"
/memory_search query:"recipe" search_type:"all" tags:"cooking"
```

**Required Permissions**: None (user's own memories)

### `/memory_list`
Displays a summary of user's stored memories.

**Parameters**:
- `sort_by` (string, optional): Sort method (date, importance, title, tags)
- `filter_tag` (string, optional): Filter by specific tag
- `date_range` (string, optional): Time range (recent, this_week, this_month, all)
- `limit` (int, optional, default: 20): Number of memories to show (1-100)

**Usage Examples**:
```
/memory_list sort_by:"date" limit:15
/memory_list filter_tag:"health" sort_by:"importance"
/memory_list date_range:"this_month" sort_by:"title"
```

**Required Permissions**: None (user's own memories)

### `/memory_edit`
Edits an existing stored memory.

**Parameters**:
- `memory_id` (string, required): ID of the memory to edit
- `field` (string, required): Field to edit (content, title, tags, importance, context)
- `new_value` (string, required): New value for the field

**Usage Examples**:
```
/memory_edit memory_id:"mem_12345" field:"title" new_value:"Updated Meeting with Sarah"
/memory_edit memory_id:"mem_12345" field:"importance" new_value:"high"
/memory_edit memory_id:"mem_12345" field:"tags" new_value:"coffee,friend,main-street,updated"
```

**Required Permissions**: None (user's own memories)

### `/memory_delete`
Removes a stored memory.

**Parameters**:
- `memory_id` (string, required): ID of the memory to delete
- `confirm` (boolean, required): Confirmation flag (must be true)

**Usage Examples**:
```
/memory_delete memory_id:"mem_12345" confirm:true
```

**Required Permissions**: None (user's own memories)

### `/memory_export`
Exports user's memories in various formats.

**Parameters**:
- `format` (string, optional): Export format (json, txt, csv)
- `filter_tag` (string, optional): Export only memories with specific tag
- `include_metadata` (boolean, optional, default: true): Include metadata like timestamps and IDs

**Usage Examples**:
```
/memory_export format:"json" include_metadata:true
/memory_export format:"txt" filter_tag:"health"
/memory_export format:"csv"
```

**Required Permissions**: None (user's own memories)

## Technical Implementation

### Class Structure
```python
class EpisodicMemory(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    
    # Command handlers
    async def memory_store_command(self, interaction: discord.Interaction,
                                  content: str, title: str = None, tags: str = None,
                                  importance: str = "medium", context: str = None)
    
    async def memory_search_command(self, interaction: discord.Interaction,
                                   query: str, search_type: str = "content",
                                   tags: str = None, date_range: str = "all", limit: int = 10)
    
    async def memory_list_command(self, interaction: discord.Interaction,
                                 sort_by: str = "date", filter_tag: str = None,
                                 date_range: str = "all", limit: int = 20)
    
    async def memory_edit_command(self, interaction: discord.Interaction,
                                 memory_id: str, field: str, new_value: str)
    
    async def memory_delete_command(self, interaction: discord.Interaction,
                                   memory_id: str, confirm: bool)
    
    async def memory_export_command(self, interaction: discord.Interaction,
                                   format: str = "json", filter_tag: str = None,
                                   include_metadata: bool = True)
    
    # Core functionality
    async def store_memory(self, user_id: str, memory_data: dict) -> str
    async def search_memories(self, user_id: str, query: str, filters: dict) -> List[Memory]
    async def get_user_memories(self, user_id: str, filters: dict = None) -> List[Memory]
    async def update_memory(self, memory_id: str, user_id: str, updates: dict) -> bool
    async def delete_memory(self, memory_id: str, user_id: str) -> bool
```

### Memory Data Models
```python
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
import uuid

class ImportanceLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class MemoryType(Enum):
    PERSONAL = "personal"
    CONVERSATION = "conversation"
    CONTEXT = "context"
    LEARNING = "learning"
    EXPERIENCE = "experience"

class SearchType(Enum):
    CONTENT = "content"
    TAGS = "tags"
    TITLE = "title"
    ALL = "all"

@dataclass
class Memory:
    id: str
    user_id: str
    title: Optional[str]
    content: str
    memory_type: MemoryType
    tags: List[str]
    importance: ImportanceLevel
    context: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    # Search and analysis fields
    keywords: List[str] = None
    sentiment_score: float = 0.0
    relevance_score: float = 0.0
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    
    # Relationships and connections
    related_memories: List[str] = None  # Memory IDs
    parent_memory: Optional[str] = None  # Parent memory ID
    
    # Metadata
    source_channel: Optional[str] = None
    source_message: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'content': self.content,
            'memory_type': self.memory_type.value,
            'tags': self.tags,
            'importance': self.importance.value,
            'context': self.context,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'keywords': self.keywords or [],
            'sentiment_score': self.sentiment_score,
            'relevance_score': self.relevance_score,
            'access_count': self.access_count,
            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None,
            'related_memories': self.related_memories or [],
            'parent_memory': self.parent_memory,
            'source_channel': self.source_channel,
            'source_message': self.source_message,
            'metadata': self.metadata or {}
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Memory':
        return cls(
            id=data['id'],
            user_id=data['user_id'],
            title=data.get('title'),
            content=data['content'],
            memory_type=MemoryType(data['memory_type']),
            tags=data.get('tags', []),
            importance=ImportanceLevel(data['importance']),
            context=data.get('context'),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            keywords=data.get('keywords', []),
            sentiment_score=data.get('sentiment_score', 0.0),
            relevance_score=data.get('relevance_score', 0.0),
            access_count=data.get('access_count', 0),
            last_accessed=datetime.fromisoformat(data['last_accessed']) if data.get('last_accessed') else None,
            related_memories=data.get('related_memories', []),
            parent_memory=data.get('parent_memory'),
            source_channel=data.get('source_channel'),
            source_message=data.get('source_message'),
            metadata=data.get('metadata', {})
        )
    
    def add_tag(self, tag: str):
        """Add a tag to the memory"""
        if tag.lower() not in [t.lower() for t in self.tags]:
            self.tags.append(tag)
            self.updated_at = datetime.now()
    
    def remove_tag(self, tag: str):
        """Remove a tag from the memory"""
        self.tags = [t for t in self.tags if t.lower() != tag.lower()]
        self.updated_at = datetime.now()
    
    def increment_access(self):
        """Increment access count and update last accessed time"""
        self.access_count += 1
        self.last_accessed = datetime.now()
    
    def update_relevance_score(self, query: str, context: str = None):
        """Update relevance score based on query and context"""
        
        query_words = set(query.lower().split())
        content_words = set(self.content.lower().split())
        title_words = set(self.title.lower().split()) if self.title else set()
        
        # Calculate content similarity
        content_overlap = len(query_words.intersection(content_words))
        title_overlap = len(query_words.intersection(title_words))
        
        # Base score from overlaps
        base_score = content_overlap + (title_overlap * 2)  # Title words worth more
        
        # Tag bonus
        tag_score = sum(1 for tag in self.tags if tag.lower() in query_words)
        
        # Importance bonus
        importance_bonus = {
            ImportanceLevel.LOW: 0,
            ImportanceLevel.MEDIUM: 1,
            ImportanceLevel.HIGH: 2,
            ImportanceLevel.CRITICAL: 3
        }
        
        # Context bonus
        context_bonus = 0
        if context and context.lower() in self.content.lower():
            context_bonus = 2
        
        # Access frequency bonus (recent memories get boost)
        access_bonus = min(self.access_count, 5)  # Max 5 points
        
        self.relevance_score = base_score + tag_score + importance_bonus[self.importance] + context_bonus + access_bonus
```

### Memory Database Management
```python
import sqlite3
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

class MemoryDatabase:
    def __init__(self, db_path: str = "data/episodic_memory.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize memory database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT,
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    tags TEXT,  -- JSON array
                    importance TEXT NOT NULL,
                    context TEXT,
                    keywords TEXT,  -- JSON array
                    sentiment_score REAL DEFAULT 0.0,
                    relevance_score REAL DEFAULT 0.0,
                    access_count INTEGER DEFAULT 0,
                    last_accessed DATETIME,
                    related_memories TEXT,  -- JSON array
                    parent_memory TEXT,
                    source_channel TEXT,
                    source_message TEXT,
                    metadata TEXT,  -- JSON object
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_user_date 
                ON memories (user_id, created_at)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_tags 
                ON memories (tags) 
                WHERE tags IS NOT NULL
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_importance 
                ON memories (importance)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_search 
                ON memories (content, title, tags)  -- Full-text search optimization
            """)
    
    def create_memory(self, memory: Memory) -> bool:
        """Create a new memory in the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO memories 
                    (id, user_id, title, content, memory_type, tags, importance, context,
                     keywords, sentiment_score, relevance_score, access_count, last_accessed,
                     related_memories, parent_memory, source_channel, source_message, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    memory.id,
                    memory.user_id,
                    memory.title,
                    memory.content,
                    memory.memory_type.value,
                    json.dumps(memory.tags) if memory.tags else None,
                    memory.importance.value,
                    memory.context,
                    json.dumps(memory.keywords) if memory.keywords else None,
                    memory.sentiment_score,
                    memory.relevance_score,
                    memory.access_count,
                    memory.last_accessed.isoformat() if memory.last_accessed else None,
                    json.dumps(memory.related_memories) if memory.related_memories else None,
                    memory.parent_memory,
                    memory.source_channel,
                    memory.source_message,
                    json.dumps(memory.metadata) if memory.metadata else None
                ))
                
                return True
                
        except Exception as e:
            await func.report_error(e, "create_memory")
            return False
    
    def search_memories(self, user_id: str, query: str, filters: Dict[str, Any] = None) -> List[Memory]:
        """Search memories with advanced filtering"""
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Build base query
                base_query = """
                    SELECT * FROM memories 
                    WHERE user_id = ?
                """
                params = [user_id]
                
                # Add search conditions
                if filters:
                    if 'search_type' in filters:
                        search_type = filters['search_type']
                        if search_type == 'content' or search_type == 'all':
                            base_query += " AND (content LIKE ? OR title LIKE ?)"
                            search_term = f"%{query}%"
                            params.extend([search_term, search_term])
                        elif search_type == 'title':
                            base_query += " AND title LIKE ?"
                            params.append(f"%{query}%")
                        elif search_type == 'tags':
                            base_query += " AND tags LIKE ?"
                            params.append(f"%{query}%")
                    
                    # Add tag filter
                    if 'tags' in filters and filters['tags']:
                        tag_filter = filters['tags']
                        base_query += " AND tags LIKE ?"
                        params.append(f"%{tag_filter}%")
                    
                    # Add importance filter
                    if 'importance' in filters and filters['importance']:
                        base_query += " AND importance = ?"
                        params.append(filters['importance'])
                    
                    # Add date range filter
                    if 'date_range' in filters and filters['date_range'] != 'all':
                        date_filter = self._get_date_filter(filters['date_range'])
                        if date_filter:
                            base_query += " AND created_at >= ?"
                            params.append(date_filter.isoformat())
                
                base_query += " ORDER BY relevance_score DESC, created_at DESC"
                
                # Add limit
                if 'limit' in filters:
                    base_query += " LIMIT ?"
                    params.append(filters['limit'])
                else:
                    base_query += " LIMIT 50"
                
                cursor = conn.execute(base_query, params)
                
                memories = []
                for row in cursor:
                    memory = self._row_to_memory(row)
                    if memory:
                        memories.append(memory)
                
                return memories
                
        except Exception as e:
            await func.report_error(e, "search_memories")
            return []
    
    def get_user_memories(self, user_id: str, filters: Dict[str, Any] = None) -> List[Memory]:
        """Get all memories for a user with optional filters"""
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Build query
                query = "SELECT * FROM memories WHERE user_id = ?"
                params = [user_id]
                
                # Add filters
                if filters:
                    if 'sort_by' in filters:
                        sort_field = self._get_sort_field(filters['sort_by'])
                        sort_order = "DESC" if filters.get('sort_order', 'desc') == 'desc' else "ASC"
                        query += f" ORDER BY {sort_field} {sort_order}"
                    else:
                        query += " ORDER BY created_at DESC"
                    
                    if 'limit' in filters:
                        query += " LIMIT ?"
                        params.append(filters['limit'])
                    
                    if 'filter_tag' in filters and filters['filter_tag']:
                        query += " AND tags LIKE ?"
                        params.append(f"%{filters['filter_tag']}%")
                    
                    if 'date_range' in filters and filters['date_range'] != 'all':
                        date_filter = self._get_date_filter(filters['date_range'])
                        if date_filter:
                            query += " AND created_at >= ?"
                            params.append(date_filter.isoformat())
                else:
                    query += " ORDER BY created_at DESC LIMIT 50"
                
                cursor = conn.execute(query, params)
                
                memories = []
                for row in cursor:
                    memory = self._row_to_memory(row)
                    if memory:
                        memories.append(memory)
                
                return memories
                
        except Exception as e:
            await func.report_error(e, "get_user_memories")
            return []
    
    def update_memory(self, memory_id: str, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing memory"""
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Verify ownership
                cursor = conn.execute(
                    "SELECT id FROM memories WHERE id = ? AND user_id = ?",
                    (memory_id, user_id)
                )
                
                if not cursor.fetchone():
                    return False  # Memory not found or not owned by user
                
                # Build update query
                set_clauses = []
                params = []
                
                for field, value in updates.items():
                    if field in ['tags', 'keywords', 'related_memories']:
                        set_clauses.append(f"{field} = ?")
                        params.append(json.dumps(value) if value else None)
                    elif field == 'last_accessed':
                        set_clauses.append(f"{field} = ?")
                        params.append(value.isoformat() if value else None)
                    elif field in ['title', 'content', 'context', 'memory_type', 'importance']:
                        set_clauses.append(f"{field} = ?")
                        params.append(value.value if hasattr(value, 'value') else value)
                    elif field == 'metadata':
                        set_clauses.append(f"{field} = ?")
                        params.append(json.dumps(value) if value else None)
                    else:
                        set_clauses.append(f"{field} = ?")
                        params.append(value)
                
                set_clauses.append("updated_at = ?")
                params.append(datetime.now().isoformat())
                
                params.extend([memory_id, user_id])
                
                query = f"""
                    UPDATE memories 
                    SET {', '.join(set_clauses)}
                    WHERE id = ? AND user_id = ?
                """
                
                conn.execute(query, params)
                return True
                
        except Exception as e:
            await func.report_error(e, "update_memory")
            return False
    
    def delete_memory(self, memory_id: str, user_id: str) -> bool:
        """Delete a memory"""
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Verify ownership
                cursor = conn.execute(
                    "SELECT id FROM memories WHERE id = ? AND user_id = ?",
                    (memory_id, user_id)
                )
                
                if not cursor.fetchone():
                    return False  # Memory not found or not owned by user
                
                # Delete memory
                conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                
                return True
                
        except Exception as e:
            await func.report_error(e, "delete_memory")
            return False
    
    def _row_to_memory(self, row) -> Optional[Memory]:
        """Convert database row to Memory object"""
        
        try:
            # Parse JSON fields
            tags = json.loads(row['tags']) if row['tags'] else []
            keywords = json.loads(row['keywords']) if row['keywords'] else []
            related_memories = json.loads(row['related_memories']) if row['related_memories'] else []
            metadata = json.loads(row['metadata']) if row['metadata'] else {}
            
            # Convert datetime fields
            created_at = datetime.fromisoformat(row['created_at'])
            updated_at = datetime.fromisoformat(row['updated_at'])
            last_accessed = datetime.fromisoformat(row['last_accessed']) if row['last_accessed'] else None
            
            return Memory(
                id=row['id'],
                user_id=row['user_id'],
                title=row['title'],
                content=row['content'],
                memory_type=MemoryType(row['memory_type']),
                tags=tags,
                importance=ImportanceLevel(row['importance']),
                context=row['context'],
                created_at=created_at,
                updated_at=updated_at,
                keywords=keywords,
                sentiment_score=row['sentiment_score'],
                relevance_score=row['relevance_score'],
                access_count=row['access_count'],
                last_accessed=last_accessed,
                related_memories=related_memories,
                parent_memory=row['parent_memory'],
                source_channel=row['source_channel'],
                source_message=row['source_message'],
                metadata=metadata
            )
            
        except Exception as e:
            await func.report_error(e, "row_to_memory")
            return None
    
    def _get_date_filter(self, date_range: str) -> Optional[datetime]:
        """Get date filter based on range"""
        
        now = datetime.now()
        
        if date_range == "recent":
            return now - timedelta(hours=24)
        elif date_range == "this_week":
            return now - timedelta(weeks=1)
        elif date_range == "this_month":
            return now - timedelta(days=30)
        elif date_range == "last_week":
            return now - timedelta(weeks=1)
        elif date_range == "last_month":
            return now - timedelta(days=30)
        elif date_range == "last_year":
            return now - timedelta(days=365)
        else:
            return None
    
    def _get_sort_field(self, sort_by: str) -> str:
        """Get database field name for sorting"""
        
        sort_mapping = {
            'date': 'created_at',
            'title': 'title',
            'importance': 'importance',
            'relevance': 'relevance_score',
            'access': 'access_count',
            'updated': 'updated_at'
        }
        
        return sort_mapping.get(sort_by, 'created_at')
```

### Context Analysis Engine
```python
import re
from typing import List, Dict, Any, Optional
from collections import Counter
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.tag import pos_tag
from nltk.stem import WordNetLemmatizer

class ContextAnalyzer:
    def __init__(self):
        # Initialize NLTK components
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')
        
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords')
        
        try:
            nltk.data.find('taggers/averaged_perceptron_tagger')
        except LookupError:
            nltk.download('averaged_perceptron_tagger')
        
        try:
            nltk.data.find('corpora/wordnet')
        except LookupError:
            nltk.download('wordnet')
        
        self.stop_words = set(stopwords.words('english'))
        self.lemmatizer = WordNetLemmatizer()
        
        # Context patterns
        self.context_indicators = {
            'location': ['at', 'in', 'near', 'by', 'location', 'place', 'venue'],
            'time': ['when', 'time', 'date', 'hour', 'minute', 'day', 'week', 'month', 'year'],
            'person': ['with', 'met', 'saw', 'talked', 'spoke', 'person', 'people', 'friend'],
            'activity': ['doing', 'doing', 'activity', 'task', 'work', 'project'],
            'emotion': ['felt', 'felt', 'emotion', 'happy', 'sad', 'excited', 'worried']
        }

    def extract_context(self, content: str) -> Dict[str, Any]:
        """Extract context information from memory content"""
        
        context = {
            'entities': [],
            'time_references': [],
            'locations': [],
            'activities': [],
            'emotions': [],
            'keywords': [],
            'sentiment': 0.0
        }
        
        try:
            # Tokenize and analyze
            sentences = sent_tokenize(content)
            words = word_tokenize(content.lower())
            
            # Extract named entities (simplified)
            context['entities'] = self._extract_entities(content)
            
            # Extract time references
            context['time_references'] = self._extract_time_references(content)
            
            # Extract locations
            context['locations'] = self._extract_locations(content)
            
            # Extract activities
            context['activities'] = self._extract_activities(words)
            
            # Extract emotions
            context['emotions'] = self._extract_emotions(content)
            
            # Extract keywords
            context['keywords'] = self._extract_keywords(words)
            
            # Calculate sentiment
            context['sentiment'] = self._calculate_sentiment(content)
            
        except Exception as e:
            await func.report_error(e, "extract_context")
        
        return context
    
    def _extract_entities(self, content: str) -> List[str]:
        """Extract named entities from content"""
        
        # Simple entity extraction using POS tagging
        words = word_tokenize(content)
        pos_tags = pos_tag(words)
        
        entities = []
        current_entity = []
        
        for word, tag in pos_tags:
            # Look for proper nouns (NNP, NNPS)
            if tag in ['NNP', 'NNPS']:
                current_entity.append(word)
            else:
                if current_entity:
                    entities.append(' '.join(current_entity))
                    current_entity = []
        
        # Add final entity if exists
        if current_entity:
            entities.append(' '.join(current_entity))
        
        return entities
    
    def _extract_time_references(self, content: str) -> List[str]:
        """Extract time-related references"""
        
        time_patterns = [
            r'\b(\d{1,2}:\d{2}\s*(am|pm)?)\b',
            r'\b(today|yesterday|tomorrow|now|then)\b',
            r'\b(this|next|last)\s*(week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
            r'\b(\d{1,2}/\d{1,2}(/\d{2,4})?)\b',
            r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\b'
        ]
        
        time_refs = []
        for pattern in time_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            time_refs.extend(matches)
        
        return time_refs
    
    def _extract_locations(self, content: str) -> List[str]:
        """Extract location references"""
        
        location_keywords = ['at', 'in', 'near', 'by', 'location', 'place', 'venue', 'street', 'avenue', 'road']
        words = word_tokenize(content.lower())
        pos_tags = pos_tag(words)
        
        locations = []
        
        for i, (word, tag) in enumerate(pos_tags):
            if word in location_keywords and i + 1 < len(pos_tags):
                # Look for noun after location keyword
                next_word, next_tag = pos_tags[i + 1]
                if next_tag.startswith('NN'):
                    locations.append(next_word)
        
        return list(set(locations))  # Remove duplicates
    
    def _extract_activities(self, words: List[str]) -> List[str]:
        """Extract activity references"""
        
        # Common activity words
        activity_words = {'meeting', 'appointment', 'shopping', 'dining', 'travel', 'work', 'exercise', 'reading', 'watching', 'playing'}
        
        activities = []
        for word in words:
            if word in activity_words:
                activities.append(word)
        
        return activities
    
    def _extract_emotions(self, content: str) -> List[str]:
        """Extract emotion references"""
        
        emotion_words = {
            'positive': ['happy', 'excited', 'joyful', 'pleased', 'satisfied', 'delighted', 'thrilled'],
            'negative': ['sad', 'upset', 'worried', 'anxious', 'frustrated', 'disappointed', 'angry'],
            'neutral': ['calm', 'content', 'indifferent', 'neutral', 'normal']
        }
        
        emotions = []
        content_lower = content.lower()
        
        for category, words in emotion_words.items():
            for word in words:
                if word in content_lower:
                    emotions.append(word)
        
        return emotions
    
    def _extract_keywords(self, words: List[str]) -> List[str]:
        """Extract meaningful keywords"""
        
        # Remove stop words and lemmatize
        filtered_words = [self.lemmatizer.lemmatize(word) for word in words 
                         if word.isalpha() and len(word) > 2 and word not in self.stop_words]
        
        # Get most frequent words
        word_freq = Counter(filtered_words)
        return [word for word, count in word_freq.most_common(10)]
    
    def _calculate_sentiment(self, content: str) -> float:
        """Calculate sentiment score (-1 to 1)"""
        
        # Simple sentiment analysis using word lists
        positive_words = {
            'good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic', 'awesome', 
            'happy', 'joy', 'pleased', 'satisfied', 'delighted', 'excited', 'love', 'like'
        }
        
        negative_words = {
            'bad', 'terrible', 'awful', 'horrible', 'disgusting', 'sad', 'angry', 'upset',
            'disappointed', 'frustrated', 'annoyed', 'hate', 'dislike', 'worried', 'anxious'
        }
        
        words = word_tokenize(content.lower())
        positive_count = sum(1 for word in words if word in positive_words)
        negative_count = sum(1 for word in words if word in negative_words)
        
        total_words = len(words)
        if total_words == 0:
            return 0.0
        
        sentiment = (positive_count - negative_count) / total_words
        return max(-1.0, min(1.0, sentiment))  # Clamp between -1 and 1
    
    def find_related_memories(self, current_memory: Memory, user_memories: List[Memory]) -> List[str]:
        """Find related memories based on content similarity"""
        
        related_ids = []
        current_keywords = set(current_memory.keywords or [])
        current_tags = set(tag.lower() for tag in current_memory.tags)
        
        for memory in user_memories:
            if memory.id == current_memory.id:
                continue
            
            # Calculate similarity score
            similarity_score = 0
            
            # Keyword overlap
            memory_keywords = set(memory.keywords or [])
            keyword_overlap = len(current_keywords.intersection(memory_keywords))
            similarity_score += keyword_overlap * 2
            
            # Tag overlap
            memory_tags = set(tag.lower() for tag in memory.tags)
            tag_overlap = len(current_tags.intersection(memory_tags))
            similarity_score += tag_overlap * 3
            
            # Content similarity (simple word overlap)
            current_words = set(current_memory.content.lower().split())
            memory_words = set(memory.content.lower().split())
            content_overlap = len(current_words.intersection(memory_words))
            similarity_score += content_overlap * 0.5
            
            # Time proximity bonus
            if memory.created_at and current_memory.created_at:
                time_diff = abs((current_memory.created_at - memory.created_at).days)
                if time_diff <= 7:  # Within a week
                    similarity_score += 1
            
            # If similarity is high enough, consider as related
            if similarity_score >= 2.0:
                related_ids.append(memory.id)
        
        return related_ids
```

### Memory Analytics
```python
from datetime import datetime, timedelta
from typing import Dict, Any, List

class MemoryAnalytics:
    def __init__(self, memory_db: MemoryDatabase):
        self.db = memory_db
    
    def generate_user_insights(self, user_id: str) -> Dict[str, Any]:
        """Generate insights and analytics for user's memories"""
        
        insights = {
            'memory_count': 0,
            'memory_types': {},
            'tag_distribution': {},
            'importance_distribution': {},
            'activity_patterns': {},
            'top_keywords': [],
            'memory_growth': [],
            'engagement_metrics': {},
            'recommendations': []
        }
        
        try:
            # Get all user memories
            memories = self.db.get_user_memories(user_id, {'limit': 1000})
            insights['memory_count'] = len(memories)
            
            if not memories:
                return insights
            
            # Analyze memory types
            for memory in memories:
                memory_type = memory.memory_type.value
                insights['memory_types'][memory_type] = insights['memory_types'].get(memory_type, 0) + 1
            
            # Analyze tag distribution
            all_tags = []
            for memory in memories:
                all_tags.extend(memory.tags)
            tag_counter = Counter(all_tags)
            insights['tag_distribution'] = dict(tag_counter.most_common(10))
            
            # Analyze importance distribution
            for memory in memories:
                importance = memory.importance.value
                insights['importance_distribution'][importance] = insights['importance_distribution'].get(importance, 0) + 1
            
            # Extract top keywords
            all_keywords = []
            for memory in memories:
                all_keywords.extend(memory.keywords or [])
            keyword_counter = Counter(all_keywords)
            insights['top_keywords'] = [word for word, count in keyword_counter.most_common(10)]
            
            # Analyze activity patterns
            insights['activity_patterns'] = self._analyze_activity_patterns(memories)
            
            # Analyze memory growth over time
            insights['memory_growth'] = self._analyze_memory_growth(memories)
            
            # Calculate engagement metrics
            insights['engagement_metrics'] = self._calculate_engagement_metrics(memories)
            
            # Generate recommendations
            insights['recommendations'] = self._generate_recommendations(memories, insights)
            
        except Exception as e:
            await func.report_error(e, "generate_user_insights")
        
        return insights
    
    def _analyze_activity_patterns(self, memories: List[Memory]) -> Dict[str, Any]:
        """Analyze patterns in memory creation"""
        
        patterns = {
            'hourly_distribution': {},
            'daily_distribution': {},
            'monthly_distribution': {},
            'day_of_week_patterns': {}
        }
        
        for memory in memories:
            created_time = memory.created_at
            
            # Hour distribution
            hour = created_time.hour
            patterns['hourly_distribution'][hour] = patterns['hourly_distribution'].get(hour, 0) + 1
            
            # Day distribution
            day = created_time.weekday()
            patterns['day_of_week_patterns'][day] = patterns['day_of_week_patterns'].get(day, 0) + 1
            
            # Month distribution
            month_key = f"{created_time.year}-{created_time.month:02d}"
            patterns['monthly_distribution'][month_key] = patterns['monthly_distribution'].get(month_key, 0) + 1
        
        return patterns
    
    def _analyze_memory_growth(self, memories: List[Memory]) -> List[Dict[str, Any]]:
        """Analyze memory creation growth over time"""
        
        # Group memories by month
        monthly_counts = {}
        for memory in memories:
            month_key = f"{memory.created_at.year}-{memory.created_at.month:02d}"
            monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
        
        # Convert to trend data
        growth_data = []
        total_memories = 0
        
        for month in sorted(monthly_counts.keys()):
            count = monthly_counts[month]
            total_memories += count
            growth_data.append({
                'month': month,
                'new_memories': count,
                'cumulative_total': total_memories
            })
        
        return growth_data
    
    def _calculate_engagement_metrics(self, memories: List[Memory]) -> Dict[str, Any]:
        """Calculate user engagement with their memories"""
        
        if not memories:
            return {}
        
        total_accesses = sum(memory.access_count for memory in memories)
        avg_accesses = total_accesses / len(memories)
        
        # Recent activity (last 30 days)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent_memories = [m for m in memories if m.created_at >= thirty_days_ago]
        
        return {
            'total_memory_accesses': total_accesses,
            'average_accesses_per_memory': round(avg_accesses, 2),
            'most_accessed_memory': max(memories, key=lambda m: m.access_count).title or "Untitled",
            'recent_memories_count': len(recent_memories),
            'memory_retention_rate': self._calculate_retention_rate(memories)
        }
    
    def _calculate_retention_rate(self, memories: List[Memory]) -> float:
        """Calculate memory retention rate based on access patterns"""
        
        if not memories:
            return 0.0
        
        accessed_memories = [m for m in memories if m.access_count > 0]
        retention_rate = len(accessed_memories) / len(memories)
        
        return round(retention_rate * 100, 2)
    
    def _generate_recommendations(self, memories: List[Memory], insights: Dict[str, Any]) -> List[str]:
        """Generate personalized recommendations for memory management"""
        
        recommendations = []
        
        # Memory quantity recommendations
        if insights['memory_count'] < 10:
            recommendations.append("Consider storing more memories to build a comprehensive personal knowledge base.")
        elif insights['memory_count'] > 500:
            recommendations.append("You have many memories! Consider organizing them with more specific tags for better searchability.")
        
        # Tag recommendations
        tag_count = len(insights['tag_distribution'])
        if tag_count < 5:
            recommendations.append("Try using more diverse tags to better categorize your memories.")
        elif tag_count > 20:
            recommendations.append("Consider consolidating similar tags to improve organization.")
        
        # Importance distribution recommendations
        importance_dist = insights['importance_distribution']
        if importance_dist.get('critical', 0) > importance_dist.get('medium', 0):
            recommendations.append("You mark many memories as critical. Consider if all are truly critical or if some should be medium priority.")
        
        # Access pattern recommendations
        avg_accesses = insights['engagement_metrics'].get('average_accesses_per_memory', 0)
        if avg_accesses < 1:
            recommendations.append("Try reviewing your stored memories regularly to get more value from your personal knowledge base.")
        
        # Content recommendations
        if insights['memory_types'].get('conversation', 0) > insights['memory_types'].get('personal', 0):
            recommendations.append("You store many conversation memories. Consider adding more personal experiences and learnings.")
        
        return recommendations
```

## Error Handling

### Memory Error Management
```python
async def handle_memory_error(self, interaction, error, context: str, memory_id: str = None):
    """Handle memory-related errors with user-friendly messages"""
    
    error_messages = {
        "memory_not_found": f"Memory not found or you don't have permission to access it.",
        "content_too_long": "Memory content is too long. Please keep memories under 5000 characters.",
        "invalid_importance": "Invalid importance level. Use: low, medium, high, or critical.",
        "invalid_memory_type": "Invalid memory type specified.",
        "too_many_memories": "You have reached the maximum number of memories. Please delete some old ones.",
        "rate_limit_exceeded": "Memory operation rate limit exceeded. Please wait before trying again.",
        "database_error": "Database error occurred. Please try again later.",
        "export_failed": "Memory export failed. Please try again with different parameters."
    }
    
    # Determine error type and provide appropriate message
    error_str = str(error).lower()
    
    if "not found" in error_str or "no such" in error_str:
        message = error_messages["memory_not_found"]
    elif "too long" in error_str or "content" in error_str:
        message = error_messages["content_too_long"]
    elif "importance" in error_str:
        message = error_messages["invalid_importance"]
    elif "type" in error_str:
        message = error_messages["invalid_memory_type"]
    elif "too many" in error_str or "limit" in error_str:
        message = error_messages["too_many_memories"]
    elif "rate limit" in error_str or "quota" in error_str:
        message = error_messages["rate_limit_exceeded"]
    elif "export" in error_str:
        message = error_messages["export_failed"]
    else:
        message = error_messages["database_error"]
    
    await interaction.response.send_message(message, ephemeral=True)
    await func.report_error(error, f"memory_{context}_{memory_id or 'unknown'}")
```

## Usage Examples

### Storing Memories
```
User: /memory_store content:"Met Sarah at the coffee shop on Main Street today. She's a software engineer working on AI projects." title:"Meeting Sarah" tags:"coffee,friend,main-street,ai,engineer" importance:"medium"
Bot: ✅ Memory stored successfully!
Memory ID: mem_12345
Title: Meeting Sarah
Tags: coffee, friend, main-street, ai, engineer
Created: 2024-12-20 14:30

Your memory has been analyzed and 5 related keywords extracted.
```

### Searching Memories
```
User: /memory_search query:"coffee" search_type:"content" limit:5
Bot: ## Search Results for "coffee" (5 memories found)

1. **Meeting Sarah** (mem_12345) - Medium Importance
   Met Sarah at the coffee shop on Main Street today...
   Tags: coffee, friend, main-street, ai, engineer
   Created: 2024-12-20 14:30
   Relevance: 95%

2. **Morning Routine** (mem_12344) - Low Importance
   Started the day with coffee and reading...
   Tags: routine, coffee, morning, news
   Created: 2024-12-19 08:15
   Relevance: 87%
```

### Memory Analytics
```
User: /memory_list sort_by:"relevance" limit:10
Bot: ## Your Memory Summary (25 total memories)

### Recently Added:
• Meeting Sarah (2 hours ago) - Medium Importance
• Doctor Appointment (1 day ago) - High Importance
• Project Ideas (3 days ago) - Low Importance

### Most Accessed:
• Password reminder (15 accesses)
• Meeting Sarah (3 accesses)
• Recipe: Carbonara (2 accesses)

### Tag Distribution:
• work: 8 memories
• personal: 6 memories
• health: 4 memories
• cooking: 3 memories
• coffee: 2 memories

### Insights:
• You store most memories in the afternoon (14:00-16:00)
• 80% of your memories are accessed at least once
• Consider using more specific tags for better organization
```

### Memory Export
```
User: /memory_export format:"json" include_metadata:true
Bot: 📤 Memory Export Complete!

Your memories have been exported to a JSON file containing:
• 25 memories with full metadata
• Timestamps, access counts, and relevance scores
• Tag relationships and context information

File ready for download (45KB)
```

## Advanced Features

### Context-Aware Memory Recommendations
```python
class ContextualRecommender:
    def __init__(self, memory_db: MemoryDatabase, context_analyzer: ContextAnalyzer):
        self.db = memory_db
        self.analyzer = context_analyzer
    
    async def suggest_memories(self, user_id: str, current_context: str, limit: int = 5) -> List[Memory]:
        """Suggest relevant memories based on current conversation context"""
        
        # Analyze current context
        current_analysis = self.analyzer.extract_context(current_context)
        current_keywords = set(current_analysis.get('keywords', []))
        
        # Get user memories
        user_memories = self.db.get_user_memories(user_id, {'limit': 100})
        
        # Score memories based on relevance
        scored_memories = []
        for memory in user_memories:
            relevance_score = self._calculate_context_relevance(memory, current_keywords, current_analysis)
            if relevance_score > 0.3:  # Minimum relevance threshold
                scored_memories.append((memory, relevance_score))
        
        # Sort by relevance and return top suggestions
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        return [memory for memory, score in scored_memories[:limit]]
    
    def _calculate_context_relevance(self, memory: Memory, current_keywords: set, current_analysis: dict) -> float:
        """Calculate how relevant a memory is to current context"""
        
        relevance_score = 0.0
        
        # Keyword overlap
        memory_keywords = set(memory.keywords or [])
        keyword_overlap = len(current_keywords.intersection(memory_keywords))
        relevance_score += keyword_overlap * 0.4
        
        # Tag overlap
        memory_tags = set(tag.lower() for tag in memory.tags)
        current_tags = set()
        for keyword in current_keywords:
            current_tags.add(keyword.lower())
        tag_overlap = len(current_tags.intersection(memory_tags))
        relevance_score += tag_overlap * 0.3
        
        # Time relevance (recent memories more relevant)
        days_old = (datetime.now() - memory.created_at).days
        time_relevance = max(0, 1 - (days_old / 365))  # Decay over a year
        relevance_score += time_relevance * 0.2
        
        # Access frequency (frequently accessed memories are important)
        access_relevance = min(1.0, memory.access_count / 10)  # Cap at 10 accesses
        relevance_score += access_relevance * 0.1
        
        return relevance_score
```

## Configuration Options

### Bot Settings
```python
# Configuration in addons/settings.py
EPISODIC_MEMORY_CONFIG = {
    "max_memories_per_user": 1000,
    "max_memory_length": 5000,
    "max_tags_per_memory": 10,
    "supported_importance_levels": ["low", "medium", "high", "critical"],
    "supported_memory_types": ["personal", "conversation", "context", "learning", "experience"],
    "relevance_threshold": 0.3,
    "cache_enabled": True,
    "analytics_enabled": True,
    "context_analysis": {
        "enabled": True,
        "max_entities": 10,
        "max_keywords": 15,
        "sentiment_analysis": True
    }
}
```

## Integration Points

### With Other Cogs
```python
# Integration with user data for preferences
from cogs.userdata import UserData

# Integration with language manager for processing
from cogs.language_manager import LanguageManager

# Integration with AI systems for enhanced analysis
from cogs.ai_module import AIModule
```

### External Services
- **Natural Language Processing**: NLTK, spaCy for advanced text analysis
- **Vector Databases**: Pinecone, Weaviate for semantic similarity search
- **Machine Learning**: TensorFlow, PyTorch for sentiment analysis and context understanding
- **Cloud Storage**: AWS S3, Google Cloud Storage for memory backup and sync

## Related Files

- `cogs/episodic_memory.py` - Main implementation
- `data/episodic_memory.db` - SQLite database for memories
- `translations/en_US/commands/episodic_memory.json` - English translations
- `LanguageManager` - Translation system
- `addons.settings` - Configuration management

## Future Enhancements

Potential improvements:
- **Visual Memory Support**: Store and analyze images with memories
- **Memory Relationships**: Create complex relationship graphs between memories
- **Collaborative Memories**: Share and collaboratively edit memories with others
- **Memory Templates**: Pre-defined memory templates for different types of experiences
- **Voice Memory Input**: Record and process voice memories
- **Advanced AI Analysis**: Use large language models for deeper memory analysis
- **Memory Sharing**: Export memories in various formats for external use
- **Memory Privacy Controls**: Granular privacy settings for different memory categories
- **Memory Recovery**: Backup and recovery system for lost memories
- **Predictive Memory**: AI suggestions for what to remember based on patterns