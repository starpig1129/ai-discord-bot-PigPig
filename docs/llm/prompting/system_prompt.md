# System Prompt Integration

## Overview

The `system_prompt.py` module provides high-level functions for retrieving system prompts with sophisticated fallback hierarchy and three-tier inheritance. It integrates channel-level, server-level, and YAML-based prompts with automatic fallback mechanisms.

## Core Functions

### `get_channel_system_prompt(channel_id, guild_id, bot_id, message=None) -> str`

**Parameters:**
- `channel_id`: Discord channel ID
- `guild_id`: Discord server/guild ID  
- `bot_id`: Discord bot ID
- `message`: Discord message object for language detection

**Returns:**
- `str`: Complete system prompt with three-tier inheritance

**Purpose:**
Retrieves channel-specific system prompts implementing three-tier inheritance:
1. **YAML Base**: Global default configuration
2. **Server Level**: Guild-specific custom prompts
3. **Channel Level**: Channel-specific custom prompts

**Process:**
1. **Bot Instance Retrieval**: Gets bot from message context
2. **SystemPromptManager Access**: Retrieves SystemPromptManagerCog
3. **Cache Management**: Clears channel cache to ensure fresh data
4. **Prompt Retrieval**: Gets effective prompt with inheritance
5. **Source Analysis**: Determines prompt source and applicability
6. **Fallback Logic**: Returns appropriate prompt based on source

**Cache Management:**
```python
# Clear channel cache to ensure latest data
try:
    manager.cache.invalidate(guild_id, channel_id)
    _logger.debug("Cleared channel cache: %s:%s", guild_id, channel_id)
except Exception as cache_error:
    _logger.warning("Failed to clear channel cache: %s", cache_error)
```

**Source Handling:**
- **Channel/Server Level**: Returns custom prompt
- **YAML Only**: Returns empty string (handled by fallback system)
- **Unknown Source**: Returns retrieved prompt

### `get_system_prompt(bot_id, message) -> str`

**Parameters:**
- `bot_id`: Discord bot ID
- `message`: Discord message object for context

**Returns:**
- `str`: Complete system prompt string

**Purpose:**
Main entry point for system prompt retrieval with comprehensive fallback hierarchy.

**Fallback Priority Order:**
1. **Channel-Specific Prompt**: First priority if exists and valid
2. **Server-Level Prompt**: Second priority if exists and valid  
3. **YAML Global Default**: Third priority from PromptManager
4. **Hardcoded Fallback**: Final emergency prompt

**Implementation Logic:**
```python
# Try channel-specific prompt first
if message and hasattr(message, "channel") and hasattr(message, "guild"):
    try:
        channel_prompt = get_channel_system_prompt(
            str(message.channel.id), str(message.guild.id), bot_id, message
        )
        if channel_prompt and channel_prompt.strip():
            return channel_prompt
    except Exception as exc:
        # Continue to next fallback level
        pass

# Fallback to YAML prompt management system
try:
    prompt_manager = get_prompt_manager()
    if prompt_manager:
        return prompt_manager.get_system_prompt(bot_id, message)
except Exception as exc:
    # Continue to hardcoded fallback
    pass

# Final fallback: hardcoded basic prompt
```

## Three-Tier Inheritance System

### Tier 1: Channel-Level Customization
- **Source**: `SystemPromptManagerCog`
- **Priority**: Highest
- **Scope**: Individual Discord channels
- **Use Case**: Channel-specific bot behavior

### Tier 2: Server-Level Customization  
- **Source**: `SystemPromptManagerCog`
- **Priority**: Medium
- **Scope**: Entire Discord server/guild
- **Use Case**: Server-specific bot personality

### Tier 3: YAML Global Configuration
- **Source**: `PromptManager` + YAML files
- **Priority**: Base level
- **Scope**: Global bot configuration
- **Use Case**: Default bot behavior and system instructions

## Integration Architecture

**SystemPromptManagerCog Integration:**
```python
# Retrieve system prompt manager cog
system_prompt_cog = bot.get_cog("SystemPromptManagerCog")

if not system_prompt_cog:
    # Fallback to YAML system
    manager = get_prompt_manager()
    return manager.get_system_prompt(bot_id, message)

# Get effective prompt with inheritance
effective_prompt = manager.get_effective_prompt(channel_id, guild_id, message)
```

**PromptManager Integration:**
```python
# YAML-based prompt management
prompt_manager = get_prompt_manager()
return prompt_manager.get_system_prompt(bot_id, message)
```

## Error Handling

**Comprehensive Error Recovery:**
1. **Non-Fatal Failures**: Continue to next fallback level
2. **Error Reporting**: Uses `func.report_error()` for critical issues
3. **Logging**: Detailed logging for debugging and monitoring
4. **Empty String Handling**: Returns empty string for unavailable prompts

**Error Scenarios Handled:**
- Missing SystemPromptManagerCog
- Cache clearance failures  
- Prompt retrieval errors
- YAML configuration issues
- Bot instance unavailability

## Logging and Monitoring

**Debug Logging:**
- Channel and guild identification
- Cache operations
- Source determination
- Fallback progression

**Error Logging:**
- System prompt retrieval failures
- Integration errors
- Fallback activation

**Information Logging:**
- Successful prompt retrieval
- Source identification
- Performance metrics

## Performance Considerations

**Cache Management:**
- Automatic cache invalidation for freshness
- Efficient channel-level caching
- Graceful cache failure handling

**Fallback Efficiency:**
- Early termination on successful retrieval
- Minimal overhead for each fallback level
- Smart source detection

## Dependencies

- `asyncio`: For async error reporting
- `discord`: For Discord integration
- `SystemPromptManagerCog`: For channel/server prompts
- `PromptManager`: For YAML-based prompts
- `function.func`: For error handling

## Usage Examples

**Channel-Specific Prompt:**
```python
# Channel with custom prompt returns channel-level prompt
prompt = get_system_prompt(bot_id, message)
# Returns: Custom channel prompt if configured

# Channel without custom prompt falls back
prompt = get_system_prompt(bot_id, message)  
# Returns: YAML default or server-level prompt
```

**Server-Wide Configuration:**
```python
# Server with custom prompt configuration
prompt = get_system_prompt(bot_id, message)
# Returns: Server-level prompt if no channel override
```

**Global Fallback:**
```python
# No custom configuration anywhere
prompt = get_system_prompt(bot_id, message)
# Returns: YAML-based prompt or hardcoded fallback