# File Watcher Utility

## Overview

The `FileWatcher` class provides file monitoring and hot-reload functionality for the LLM system. It enables automatic detection of configuration file changes and triggers appropriate reload mechanisms.

## Class: FileWatcher

### Constructor

```python
def __init__(self, check_interval: float = 1.0):
```

**Parameters:**
- `check_interval`: Time interval in seconds between file checks (default: 1.0)

**Description:**
Initializes the file watcher with monitoring configuration and thread safety mechanisms.

**Components:**
- `watched_files`: Dictionary tracking file paths and their modification times
- `callbacks`: Dictionary mapping file paths to callback functions
- `check_interval`: Frequency of file change detection
- `_running`: Status flag for monitoring thread
- `_thread`: Background monitoring thread
- `_lock`: Thread lock for concurrent access safety

### Core Methods

#### `watch_file(self, path: str, callback: Callable)`

**Parameters:**
- `path`: File path to monitor for changes
- `callback`: Function to call when file changes are detected

**Description:**
Starts monitoring a file for modifications. Creates monitoring thread if not already running.

**Process:**
1. **File Validation**: Checks if file exists
2. **Configuration**: Records file path and modification time
3. **Callback Registration**: Associates callback function
4. **Thread Management**: Starts monitoring thread if needed

#### `_start_watching(self)`

**Description:**
Starts the background monitoring thread for file change detection.

**Thread Management:**
```python
self._thread = threading.Thread(target=self._watch_loop, daemon=True)
self._thread.start()
```

**Features:**
- **Daemon Thread**: Automatically terminates with main program
- **Background Operation**: Non-blocking file monitoring
- **Thread Safety**: Protected by RLock mechanism

### Monitoring Process

#### `_watch_loop(self)`

**Description:**
Main monitoring loop that continuously checks for file changes.

**Detection Process:**
1. **File Existence Check**: Verifies watched files still exist
2. **Modification Time Comparison**: Detects file changes via mtime
3. **Callback Execution**: Triggers registered callbacks
4. **Cleanup**: Removes deleted files from watch list

**Change Detection Logic:**
```python
current_mtime = datetime.fromtimestamp(os.path.getmtime(path))
if current_mtime > last_mtime:
    # File changed - execute callback
    self.callbacks[path](path)
    self.watched_files[path] = current_mtime
```

**Error Handling:**
- **File Access Errors**: Reported via `func.report_error()`
- **Callback Failures**: Individual callback errors don't stop monitoring
- **Missing Files**: Automatically removed from watch list

### Control Methods

#### `stop_watching(self)`

**Description:**
Stops the monitoring thread and cleans up resources.

**Cleanup Process:**
1. **Thread Termination**: Signals thread to stop
2. **Graceful Shutdown**: Waits for thread completion
3. **Resource Cleanup**: Clears watched files and callbacks

**Timeout Handling:**
```python
if self._thread and self._thread.is_alive():
    self._thread.join(timeout=2.0)
    if self._thread.is_alive():
        self.logger.warning("File watcher thread did not stop gracefully")
```

#### `check_changes(self) -> bool`

**Returns:**
- `bool`: True if any file changes were detected

**Description:**
Manually triggers file change detection without waiting for the monitoring interval.

**Use Cases:**
- Immediate configuration reload
- Debugging file monitoring
- Periodic manual checks

### File Management

#### `add_file(self, path: str, callback: Callable)`

**Parameters:**
- `path`: File path to add to monitoring
- `callback`: Callback function for changes

**Description:**
Alias for `watch_file()` method for convenience.

#### `remove_file(self, path: str)`

**Parameters:**
- `path`: File path to stop monitoring

**Description:**
Removes a file from the monitoring list.

**Cleanup Process:**
```python
self.watched_files.pop(path, None)
self.callbacks.pop(path, None)
```

### Information Methods

#### `get_watched_files(self) -> Set[str]`

**Returns:**
- `Set[str]`: Set of currently monitored file paths

**Description:**
Returns the list of all files being monitored for changes.

#### `is_watching(self, path: str) -> bool`

**Parameters:**
- `path`: File path to check

**Returns:**
- `bool`: True if the file is being monitored

**Description:**
Checks whether a specific file is currently under monitoring.

#### `get_file_info(self, path: str) -> Dict[str, Any]`

**Parameters:**
- `path`: File path to get information about

**Returns:**
- `Dict[str, Any]`: File information including status and metadata

**Information Includes:**
- File path and existence status
- Last checked modification time
- Callback association status
- File size and current modification time

**Example Response:**
```python
{
    'path': '/path/to/config.yaml',
    'last_checked': datetime(2024, 1, 15, 10, 30, 0),
    'exists': True,
    'has_callback': True,
    'size': 1024,
    'current_mtime': datetime(2024, 1, 15, 10, 35, 0)
}
```

#### `get_watcher_stats(self) -> Dict[str, Any]`

**Returns:**
- `Dict[str, Any]`: Comprehensive statistics about the watcher

**Statistics Include:**
- `is_running`: Whether monitoring thread is active
- `total_watched_files`: Total number of files being monitored
- `existing_files`: Count of files that still exist
- `missing_files`: Count of files that no longer exist
- `check_interval`: Current monitoring interval
- `thread_alive`: Whether monitoring thread is alive

### Lifecycle Management

#### `__del__(self)`

**Description:**
Destructor ensures the monitoring thread is properly stopped when the FileWatcher is garbage collected.

**Safety Feature:**
Prevents orphaned monitoring threads that could cause resource leaks.

## Integration

The FileWatcher is used by:
- **PromptManager** for configuration file monitoring
- **Orchestrator** for dynamic configuration updates
- **Settings management** for real-time configuration changes

## Dependencies

- `os`: For file system operations
- `threading`: For background monitoring thread
- `time`: For timing and intervals
- `logging`: For operation monitoring
- `datetime`: For modification time handling
- `asyncio`: For async error reporting
- `function.func`: For error handling

## Performance Considerations

**Efficient Monitoring:**
- **Interval-Based Checking**: Configurable check frequency
- **Thread Safety**: Protected concurrent access
- **Resource Management**: Automatic cleanup of missing files

**Scalability:**
- **Multiple File Support**: Can monitor unlimited files
- **Background Operation**: Non-blocking file monitoring
- **Graceful Degradation**: Continues monitoring despite individual failures

## Usage Examples

**Basic Monitoring:**
```python
watcher = FileWatcher(check_interval=1.0)

def on_config_change(path):
    print(f"Configuration file changed: {path}")
    # Reload configuration

watcher.watch_file("/path/to/config.yaml", on_config_change)
```

**Multiple Files:**
```python
watcher = FileWatcher(check_interval=2.0)

watcher.watch_file("config1.yaml", reload_config1)
watcher.watch_file("config2.yaml", reload_config2)
watcher.watch_file("prompts.yaml", reload_prompts)
```

**Manual Checking:**
```python
# Check for changes immediately
if watcher.check_changes():
    print("Files were modified")
```

**Information Retrieval:**
```python
# Get monitoring statistics
stats = watcher.get_watcher_stats()
print(f"Monitoring {stats['total_watched_files']} files")

# Check if specific file is monitored
if watcher.is_watching("/path/to/config.yaml"):
    print("File is being monitored")