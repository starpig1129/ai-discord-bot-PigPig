# Prompt Manager

## Overview

The `PromptManager` class provides a comprehensive YAML-based prompt management system that coordinates configuration loading, caching, building, and file monitoring. It serves as the central orchestrator for the prompting subsystem.

## Class: PromptManager

### Constructor

```python
def __init__(self, config_path: str = f'{prompt_config.path}/message_agent.yaml'):
```

**Parameters:**
- `config_path`: Path to YAML configuration file (default from settings)

**Description:**
Initializes the manager with all required components and performs automatic initialization.

**Components:**
- `loader`: PromptLoader for YAML file management
- `cache`: PromptCache for performance optimization
- `builder`: PromptBuilder for prompt construction
- `file_watcher`: FileWatcher for configuration change detection

### Initialization Process

#### `_initialize(self)`

**Process:**
1. **Configuration Loading**: Loads initial YAML configuration
2. **Validation**: Validates configuration structure
3. **File Monitoring**: Sets up file change detection
4. **Cache Precompilation**: Precompiles template combinations
5. **Status Tracking**: Marks manager as initialized

**Error Handling:**
Critical failures are reported and initialization is aborted.

### Configuration Management

#### `reload_prompts(self) -> bool`

**Returns:**
- `bool`: Success status of reload operation

**Process:**
1. **Cache Cleanup**: Clears all cached data
2. **Configuration Reload**: Loads fresh YAML configuration
3. **Validation**: Validates new configuration structure
4. **Cache Precompilation**: Rebuilds precompiled templates
5. **Logging**: Reports success/failure status

#### `_on_config_changed(self, path: str)`

**Parameters:**
- `path`: Path of changed configuration file

**Description:**
Callback triggered by file watcher when configuration changes. Automatically reloads prompts and reports status.

#### `_validate_config(self, config: dict) -> bool`

**Parameters:**
- `config`: Configuration dictionary to validate

**Returns:**
- `bool`: True if configuration structure is valid

**Validation Requirements:**
- Must contain required sections: `metadata`, `base`, `composition`
- Must have `composition.default_modules` defined
- Reports missing sections via logging

### Prompt Generation

#### `get_system_prompt(self, bot_id: str, message=None) -> str`

**Parameters:**
- `bot_id`: Discord bot ID
- `message`: Discord message object for language detection

**Returns:**
- `str`: Complete system prompt with dynamic replacements

**Process:**
1. **Initialization Check**: Ensures manager is initialized
2. **Language Detection**: Determines language key for caching
3. **Cache Check**: Retrieves cached prompt if available
4. **Dynamic Replacements**: Applies variable substitutions
5. **Fallback**: Returns hardcoded fallback on errors

**Cache Strategy:**
```python
cache_key = f"system_prompt_{bot_id}_{lang_key}"
cached_prompt = self.cache.get(cache_key)
if cached_prompt:
    return self._apply_dynamic_replacements(cached_prompt, bot_id, message)
```

#### `_get_language_key(self, message) -> str`

**Parameters:**
- `message`: Discord message object

**Returns:**
- `str`: Language code for caching

**Logic:**
- Attempts to get language from server settings
- Falls back to default language ("zh_TW")
- Gracefully handles missing language manager

#### `_apply_dynamic_replacements(self, prompt: str, bot_id: str, message) -> str`

**Parameters:**
- `prompt`: Base prompt template
- `bot_id`: Discord bot ID
- `message`: Discord message object

**Returns:**
- `str`: Prompt with all variables replaced

**Variable Sources:**
1. **Bot Information**: ID, owner ID, name, creator
2. **Environment**: Server context
3. **Language Data**: From LanguageManager
4. **Configuration**: From YAML base section

**Integration:**
Uses `PromptBuilder.format_with_variables()` for comprehensive variable processing.

#### `_get_fallback_prompt(self, bot_id: str) -> str`

**Parameters:**
- `bot_id`: Discord bot ID

**Returns:**
- `str`: Hardcoded fallback prompt

**Purpose:**
Provides basic functionality when YAML configuration is unavailable.

### Module Operations

#### `get_module_prompt(self, module_name: str) -> str`

**Parameters:**
- `module_name`: Name of module to retrieve

**Returns:**
- `str`: Single module prompt content

**Process:**
- Loads configuration
- Uses builder to compose single module
- Handles errors gracefully

#### `compose_prompt(self, modules: Optional[List[str]] = None) -> str`

**Parameters:**
- `modules`: List of modules to compose (None = use defaults)

**Returns:**
- `str`: Composed prompt from specified modules

**Features:**
- Safe default module access
- Type-safe parameter handling
- Error logging and graceful failure

#### `get_available_modules(self) -> List[str]`

**Returns:**
- `List[str]`: All available module names

**Logic:**
- Loads configuration
- Excludes non-module keys: metadata, composition, conditions, language_replacements
- Returns valid module names

#### `validate_modules(self, modules: List[str]) -> Dict[str, bool]`

**Parameters:**
- `modules`: List of modules to validate

**Returns:**
- `Dict[str, bool]`: Module existence validation results

**Usage:**
```python
validation = manager.validate_modules(['identity', 'language', 'nonexistent'])
# Result: {'identity': True, 'language': True, 'nonexistent': False}
```

### Monitoring and Statistics

#### `get_cache_stats(self) -> Dict[str, Any]`

**Returns:**
- `Dict[str, Any]`: Comprehensive cache statistics

**Statistics:**
- Total, active, and expired items
- Precompiled template count
- Access patterns and usage statistics

#### `get_manager_info(self) -> Dict[str, Any]`

**Returns:**
- `Dict[str, Any]`: Complete manager status information

**Information Includes:**
- Initialization status
- Configuration path and loaded status
- Available modules list
- File watcher status
- Cache statistics

### Resource Management

#### `cleanup(self)`

**Description:**
Graceful cleanup of all resources:
- Stops file watcher
- Clears cache
- Logs cleanup completion

#### `__del__(self)`

**Description:**
Destructor ensures cleanup even if manager is garbage collected.

### Instance Management

```python
_prompt_manager_instances: Dict[str, PromptManager] = {}

def get_prompt_manager(config_path: str) -> PromptManager:
```

**Purpose:**
Manages multiple PromptManager instances keyed by configuration path.

**Benefits:**
- Supports multiple agent configurations
- Prevents configuration conflicts
- Enables configuration isolation

**Usage:**
```python
# Get default manager
manager = get_prompt_manager()

# Get specific configuration
manager = get_prompt_manager("/path/to/agent2.yaml")
```

## Integration

The PromptManager is used by:
- **Orchestrator** for system prompt generation
- **SystemPromptCog** for configuration management
- **File system** for automatic reload on configuration changes

## Dependencies

- `asyncio`: For async operations
- `logging`: For monitoring and debugging
- `typing`: For type annotations
- `PromptLoader`: Configuration loading
- `PromptCache`: Performance optimization
- `PromptBuilder`: Prompt construction
- `FileWatcher`: Change detection
- `LanguageManager`: Language support