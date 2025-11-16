# Prompt Cache System

## Overview

The `PromptCache` class provides a sophisticated caching system for prompt templates and generated content. It implements TTL (Time-To-Live) management, precompilation features, thread-safe operations, and comprehensive statistics tracking.

## Class: PromptCache

### Constructor

```python
def __init__(self):
```

**Description:**
Initializes the cache system with multiple storage layers and thread safety mechanisms.

**Storage Components:**
- `cache_storage`: Main cache for prompt data
- `ttl_storage`: Timestamp tracking for expiration
- `precompiled_cache`: Precompiled template combinations
- `access_count`: Usage statistics tracking
- `_lock`: Thread lock for concurrent access safety

### Core Methods

#### `get(self, key: str) -> Optional[Any]`

**Parameters:**
- `key`: Cache key to retrieve

**Returns:**
- `Optional[Any]`: Cached value, or None if not found/expired

**Process:**
1. **Access Validation**: Checks if key exists
2. **Expiration Check**: Validates TTL using `is_expired()`
3. **Cleanup**: Automatically removes expired items
4. **Statistics**: Records access count
5. **Thread Safety**: Uses RLock for concurrent access

#### `set(self, key: str, value: Any, ttl: int = 3600) -> None`

**Parameters:**
- `key`: Cache key
- `value`: Value to cache
- `ttl`: Time-to-live in seconds (default: 3600)

**Description:**
Stores a value in the cache with expiration tracking and usage statistics initialization.

#### `invalidate(self, key: str) -> None`

**Parameters:**
- `key`: Cache key to remove

**Description:**
Completely removes a cache entry from all storage layers including main cache, TTL tracking, access statistics, and precompiled cache.

### Cache Management

#### `clear_all(self) -> None`

**Description:**
Clears all cache data across all storage layers. Logs the number of cleared items for monitoring purposes.

#### `cleanup_expired(self) -> int`

**Returns:**
- `int`: Number of expired items cleaned up

**Process:**
1. **Expiration Detection**: Scans all cached items for expiration
2. **Batch Invalidation**: Removes all expired items
3. **Statistics**: Returns count of cleaned items

#### `extend_ttl(self, key: str, additional_seconds: int) -> bool`

**Parameters:**
- `key`: Cache key to extend
- `additional_seconds`: Seconds to extend TTL

**Returns:**
- `bool`: Success status

**Description:**
Extends the TTL of an existing cache entry. Only works if the key exists and is not expired.

### Precompilation System

#### `precompile_templates(self, config: dict) -> None`

**Parameters:**
- `config`: Prompt configuration dictionary

**Description:**
Precompiles common template combinations for performance optimization:

**Precompiled Combinations:**
1. **Progressive Combinations**: All prefix combinations of default modules
   - Example: If default_modules = [base, identity, language]
   - Generates: base, base+identity, base+identity+language

2. **Individual Modules**: Each default module separately

**Precompilation Process:**
```python
# Progressive combinations
for i in range(1, len(default_modules) + 1):
    module_combo = [mod for mod in module_order if mod in default_modules[:i]]
    combo_key = '_'.join(module_combo)
    precompiled_cache[f"combo_{combo_key}"] = combo_key

# Individual modules
for module in default_modules:
    precompiled_cache[f"module_{module}"] = module
```

#### `get_precompiled(self, key: str) -> Optional[str]`

**Parameters:**
- `key`: Precompiled template key

**Returns:**
- `Optional[str]`: Precompiled template content

**Description:**
Retrieves precompiled template combinations for faster prompt generation.

### Expiration Management

#### `is_expired(self, key: str) -> bool`

**Parameters:**
- `key`: Cache key to check

**Returns:**
- `bool`: True if expired or missing

**Logic:**
- Returns True if key is missing from TTL storage
- Compares current time with stored expiration timestamp
- Used for automatic cleanup in `get()` method

### Statistics and Monitoring

#### `get_cache_stats(self) -> Dict[str, Any]`

**Returns:**
- `Dict[str, Any]`: Comprehensive cache statistics

**Statistics Include:**
- `total_items`: Total number of cached items
- `expired_items`: Count of expired items
- `active_items`: Count of non-expired items
- `precompiled_items`: Number of precompiled templates
- `total_access_count`: Sum of all access counts
- `most_accessed`: Tuple of (key, count) for most accessed item

#### `get_cache_keys(self, prefix: str = '') -> Set[str]`

**Parameters:**
- `prefix`: Optional prefix filter

**Returns:**
- `Set[str]`: Set of cache keys matching the prefix

**Description:**
Provides visibility into cached content for debugging and monitoring purposes.

## Thread Safety

The cache implementation uses `threading.RLock()` (reentrant lock) to ensure thread-safe operations:

- **Read Operations**: Multiple threads can read simultaneously
- **Write Operations**: Exclusive lock during modifications
- **Nested Calls**: Supports recursive locking within the same thread

## Performance Optimizations

1. **Precompilation**: Reduces template processing time for common combinations
2. **Lazy Expiration**: Only checks expiration during access attempts
3. **Batch Cleanup**: Efficient removal of multiple expired items
4. **Access Tracking**: Enables optimization decisions based on usage patterns

## Integration

The PromptCache is used by:
- **PromptManager** for template caching
- **Builder system** for precompiled combinations
- **Orchestrator** for prompt performance optimization

## Error Handling

All methods include comprehensive error handling:
- **Thread Safety**: All operations are protected by locks
- **Graceful Degradation**: Operations continue even if individual items fail
- **Logging**: Detailed logging for monitoring and debugging
- **Async Error Reporting**: Uses `func.report_error()` for critical issues