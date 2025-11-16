# UserData Cog Documentation

## Overview

The UserData cog provides comprehensive personal user data management capabilities, allowing users to save and retrieve their preferences, background information, and interaction rules through an AI-powered memory system. It features intelligent data merging and structured response handling.

## Features

### Core Functionality
- **Personal Memory Storage**: Save user preferences and background information
- **AI-Powered Data Merging**: Intelligent merging of existing and new user data
- **Structured Data Management**: Organized storage of user preferences, names, and interaction rules
- **Multi-language Support**: Fully localized user interface
- **Database Persistence**: SQLite-backed storage system

### Key Components
- `UserDataCog` class - Main cog implementation
- `UserDataResponse` - Pydantic schema for structured responses
- SQLite user manager integration
- LangChain AI agent for data processing

## Commands

### `/memory save`
Saves personal information that the bot should remember about the user.

**Parameters**:
- `preference`: Information to remember (e.g., "My name is John", "I prefer casual conversations")

**Behavior**: 
- AI analyzes and merges new information with existing data
- Updates structured user profile
- Provides confirmation with updated memory summary

### `/memory show`
Displays all information the bot currently remembers about the user.

**Parameters**: None

**Response**: Formatted display of saved user preferences, background, and display names

## Technical Implementation

### Class Structure
```python
class UserDataCog(commands.Cog):
    def __init__(self, bot: commands.Bot, user_manager: Optional[SQLiteUserManager] = None)
    async def cog_load(self) -> None
    async def memory_save(self, interaction: discord.Interaction, preference: str) -> None
    async def memory_show(self, interaction: discord.Interaction) -> None
    
    # Core processing methods
    async def _read_user_data(self, user_id: str, context) -> str
    async def _save_user_data(self, user_id: str, display_name: str, user_data: str, context) -> str
    async def _invoke_ai_merge_agent(self, existing_data: Optional[UserInfo], new_data: str, user_id: str) -> UserDataResponse
```

### Data Model
```python
class UserDataResponse(BaseModel):
    """Structured response schema for user data agent"""
    procedural_memory: Optional[str] = Field(
        default='',
        description="User's interaction preferences and conversation rules"
    )
    user_background: Optional[str] = Field(
        default='',
        description="User's interests, hobbies, and life background"
    )
    display_names: List[str] = Field(
        default_factory=list,
        description="Names the user wants to be called"
    )
```

### Processing Pipeline

#### Save Operation Flow
1. **Input Processing**: Receive user's preference data
2. **Existing Data Lookup**: Fetch current user information from database
3. **AI Data Merging**: Use LangChain agent to intelligently merge data
4. **Conflict Resolution**: New data takes precedence over conflicting old data
5. **Database Persistence**: Save merged data to SQLite storage
6. **Confirmation**: Return formatted summary of updated memory

#### Read Operation Flow
1. **User Resolution**: Determine target user ID
2. **Data Retrieval**: Fetch user information from database
3. **Fallback Handling**: Use message author if target user not found
4. **Formatting**: Create readable display of stored data
5. **Response**: Return formatted user data summary

### AI Integration

#### LangChain Agent Configuration
```python
agent = create_agent(
    model=model,
    tools=[],
    system_prompt=system_prompt,
    response_format=UserDataResponse,
    middleware=[
        fallback,
        ModelCallLimitMiddleware(run_limit=1, exit_behavior="end"),
    ],
)
```

#### System Prompt
```
You are a professional user data management assistant.
Intelligently merge existing user data with new data to return complete and accurate user information.
If the new data conflicts with the old data (e.g., a changed preference), the new data should take precedence and overwrite the conflicting part.
Maintain data integrity and consistency.
Always respond in Traditional Chinese.
```

#### Response Processing
1. **JSON Extraction**: Multiple strategies for extracting JSON from AI responses
2. **Validation**: Ensure response contains expected user data fields
3. **Type Checking**: Validate field types and formats
4. **Fallback Handling**: Use defaults if validation fails

### Database Integration

#### SQLite Storage System
```python
# User manager integration
from cogs.memory.users.manager import SQLiteUserManager
from cogs.memory.users.models import UserInfo

# Database operations
user_info = await self.user_manager.get_user_info(user_id)
await self.user_manager.update_user_data(user_id, merged_data, display_name)
await self.user_manager.update_user_activity(user_id, display_name)
```

#### Data Structure
- **User Information**: Structured user profile data
- **Activity Tracking**: Last interaction timestamps
- **Display Names**: Preferred name variations
- **Preferences**: Conversation rules and interaction preferences
- **Background**: Personal interests and information

## Error Handling

### Robust Fallback System
1. **Translation Fallbacks**: Localized messages when LanguageManager unavailable
2. **AI Processing Failures**: Graceful handling of AI service issues
3. **Database Errors**: Safe error reporting and recovery
4. **Data Validation**: Protection against malformed input

### Error Types Handled
- SQLite database connection issues
- AI agent processing failures
- Invalid user data formats
- Translation service unavailability
- Network timeout issues

### Recovery Strategies
- Fallback to hardcoded translation strings
- Default data structures when AI unavailable
- User-friendly error messages
- Automatic retry mechanisms where appropriate

## Configuration

### Dependencies
- **Database**: SQLite with user manager
- **AI**: LangChain with structured responses
- **Models**: Configurable AI model selection
- **Translation**: LanguageManager integration

### Model Configuration
```python
# Model selection from config
model, fallback = ModelManager().get_model("user_data_model")
```

### Database Settings
- **Storage Location**: Configured through user manager
- **Schema**: Automatically managed by SQLiteUserManager
- **Backup**: Regular data persistence

## Performance Considerations

### Efficient Data Processing
- **Structured Responses**: Fast JSON parsing and validation
- **Caching**: Database query optimization
- **Async Operations**: Non-blocking database and AI operations
- **Memory Management**: Efficient data structure handling

### Scalability
- **Database Indexing**: Optimized user ID lookups
- **Batch Operations**: Efficient bulk data processing
- **Connection Pooling**: Database connection management

## Security & Permissions

### Access Control
- **Personal Data**: Users can only access their own data
- **Bot Owner Access**: Owner-only administrative commands
- **Data Isolation**: Strict user data separation

### Privacy Protection
- **Encrypted Storage**: Sensitive data protection
- **Access Logging**: Audit trail for data access
- **Data Retention**: Configurable data retention policies

## Usage Examples

### Saving User Information
```
User: /memory save I love hiking and outdoor activities
Bot: "Got it! I've remembered it!
My updated memory:
Preference: User loves hiking and outdoor activities
Background: User enjoys outdoor activities and nature
Display Names: [user's current display name]"
```

### Viewing Saved Data
```
User: /memory show
Bot: "I currently remember about you:
Preference: User loves hiking and outdoor activities
Background: User enjoys outdoor activities and nature
Display Names: John Doe, John"
```

### Data Merging Example
```
Existing: "I prefer formal conversations"
New: "I like casual chats with friends"
Result: "I prefer casual conversations with friends"
```

## Related Files

- `cogs/userdata.py` - Main implementation
- `cogs/memory/users/manager.py` - SQLite user manager
- `cogs/memory/users/models.py` - User data models
- `LanguageManager` - Translation system
- `ModelManager` - AI model configuration

## Future Enhancements

Potential improvements:
- Data export/import functionality
- Advanced search capabilities
- Data analytics and insights
- Collaborative memory features
- Integration with other AI services
- Enhanced data validation rules
- Backup and restore capabilities