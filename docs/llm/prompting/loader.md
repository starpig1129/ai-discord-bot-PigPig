# Prompt Configuration Loader

## Overview

The `PromptLoader` class is responsible for loading and managing YAML configuration files for the prompting system. It provides file change detection, caching mechanisms, and configuration validation capabilities.

## Class: PromptLoader

### Constructor

```python
def __init__(self, config_path: str = f'{prompt_config.path}/message_agent.yaml'):
```

**Parameters:**
- `config_path`: Path to the YAML configuration file (default: from settings)

**Description:**
Initializes the loader with file path and caching mechanisms. The default path uses the `prompt_config.path` from settings.

**Initialization Components:**
- `config_path`: YAML configuration file path
- `_cached_config`: Cached configuration dictionary
- `_last_loaded`: Timestamp of last successful load

### Core Methods

#### `load_yaml_config(self) -> Dict[str, Any]`

**Returns:**
- `Dict[str, Any]`: Parsed configuration dictionary

**Process:**
1. **File Validation**: Checks file existence
2. **File Reading**: Loads file with UTF-8 encoding
3. **YAML Parsing**: Uses `yaml.safe_load()` for secure parsing
4. **Cache Update**: Updates cached configuration and timestamp
5. **Validation**: Ensures non-empty configuration

**Error Handling:**
- `FileNotFoundError`: Configuration file doesn't exist
- `yaml.YAMLError`: YAML parsing fails
- `ValueError`: Empty or invalid YAML content

#### `reload_if_changed(self) -> bool`

**Returns:**
- `bool`: True if configuration was reloaded

**Process:**
1. **File Existence Check**: Verifies file still exists
2. **Modification Time**: Gets current file modification timestamp
3. **Change Detection**: Compares with last loaded time
4. **Conditional Reload**: Loads new configuration if changed
5. **Logging**: Reports reload activity

**Use Case:**
Called before operations to ensure cached data is current, preventing stale configuration usage.

### Configuration Access

#### `get_cached_config(self) -> Optional[Dict[str, Any]]`

**Returns:**
- `Optional[Dict[str, Any]]`: Current cached configuration

**Description:**
Smart getter that:
1. **Auto-Reload**: Detects file changes and reloads if necessary
2. **Graceful Fallback**: Returns cached data even if reload fails
3. **Freshness Check**: Ensures latest configuration is used

**Implementation:**
```python
def get_cached_config(self):
    try:
        self.reload_if_changed()
    except Exception:
        # Return whatever is cached, report non-fatally
        pass
    return self._cached_config
```

#### `get_config_section(self, section_name: str) -> Optional[Dict[str, Any]]`

**Parameters:**
- `section_name`: Name of configuration section to retrieve

**Returns:**
- `Optional[Dict[str, Any]]`: Configuration section data

**Process:**
1. **Lazy Loading**: Loads configuration if not cached
2. **Freshness Check**: Reloads if file changed since last load
3. **Section Extraction**: Returns specific section from config

**Error Handling:**
Non-fatal failures: logs warning and returns available cached data.

### File Management

#### `get_last_modified(self) -> Optional[datetime]`

**Returns:**
- `Optional[datetime]`: Last modification time, or None if file doesn't exist

**Description:**
Returns the file's last modification timestamp for change detection purposes.

#### `is_config_loaded(self) -> bool`

**Returns:**
- `bool`: True if configuration is cached

**Description:**
Simple check to determine if configuration has been loaded into cache.

### Configuration Validation

#### `validate_config_structure(self, config: Dict[str, Any]) -> bool`

**Parameters:**
- `config`: Configuration dictionary to validate

**Returns:**
- `bool`: True if configuration structure is valid

**Validation Requirements:**

**Required Top-Level Sections:**
1. `metadata`: Configuration metadata
2. `base`: Base prompt configuration
3. `composition`: Module composition rules

**Required Composition Fields:**
- `default_modules`: List of default modules to include

**Validation Process:**
1. **Section Check**: Verifies all required sections exist
2. **Module Validation**: Confirms default modules are defined
3. **Warning Generation**: Logs warnings for missing modules

**Example Validation:**
```python
required_sections = ['metadata', 'base', 'composition']

# Check for required sections
for section in required_sections:
    if section not in config:
        logger.error(f"Missing required section: {section}")
        return False

# Check default modules
composition = config.get('composition', {})
if 'default_modules' not in composition:
    logger.error("Missing 'default_modules' in composition section")
    return False
```

## File Change Detection

The loader implements sophisticated file change detection:

1. **Timestamp Comparison**: Uses file modification time
2. **Lazy Reloading**: Only reloads when actually needed
3. **Caching Strategy**: Avoids redundant file reads
4. **Error Recovery**: Continues with cached data on failures

## Integration

The PromptLoader is used by:
- **PromptManager** for configuration loading
- **Orchestrator** for system prompt generation
- **Cache system** for template precompilation

## Dependencies

- `yaml`: For YAML file parsing
- `os`: For file system operations
- `datetime`: For timestamp handling
- `addons.settings`: For configuration path
- `function.func`: For error reporting

## Performance Considerations

- **Lazy Loading**: Configuration loaded only when needed
- **Change Detection**: Avoids unnecessary file reads
- **Cache Efficiency**: Stores parsed configuration for reuse
- **Error Resilience**: Continues operating with stale data if needed