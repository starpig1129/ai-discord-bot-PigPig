# Prompt Builder

## Overview

The `PromptBuilder` class is responsible for constructing dynamic system prompts for the LLM system. It processes YAML configuration files, handles language localization, manages variable substitutions, and provides flexible prompt generation capabilities.

## Class: PromptBuilder

### Constructor

```python
def __init__(self):
```

**Description:**
Initializes the prompt builder with logging configuration and module title mappings for formatting different types of prompt modules.

**Module Title Mapping:**
The builder maintains predefined titles for different module types:
- `base`: Core instruction (no title)
- `identity`: "Identity and Role"
- `response_principles`: "Response Principles" 
- `language`: "Language Requirements (語言要求)"
- `output_format`: "Output Format Rules"
- `input_parsing`: "Input Parsing"
- `memory_system`: "Memory System"
- `information_handling`: "Information Handling"
- `error_handling`: "Error Handling"
- `interaction`: "Interaction"
- `professional_personality`: "Professional Personality"

### Core Methods

#### `build_system_prompt(self, config: dict, modules: List[str]) -> str`

**Parameters:**
- `config`: Configuration dictionary containing module definitions
- `modules`: List of module names to include in the prompt

**Returns:**
- `str`: Complete assembled system prompt

**Description:**
Builds a complete system prompt by combining modules in a specified order. Uses the `composition.module_order` from config to determine the sequence of modules.

**Process:**
1. Retrieves module order from config
2. Iterates through modules in order
3. Formats each module using `_format_module_content()`
4. Combines all parts with double newlines

#### `format_with_variables(self, prompt: str, variables: dict, lang_manager=None, guild_id: Union[str, None] = None) -> str`

**Parameters:**
- `prompt`: Prompt template containing variables
- `variables`: Dictionary of variables for substitution
- `lang_manager`: LanguageManager instance for localization
- `guild_id`: Discord server ID for language-specific translations

**Returns:**
- `str`: Formatted prompt with variables replaced

**Description:**
Handles comprehensive variable substitution including:
1. **Language Placeholder Resolution**: Processes `{{lang.xxx}}` and `{lang.xxx}` patterns
2. **Variable Substitution**: Replaces `{variable_name}` placeholders
3. **Fallback Processing**: Uses `.format()` method as fallback for complex cases

**Language Replacement Strategy:**
```python
# Supports both double and single brace patterns
{{lang.system.chat_bot.language.answer_in}} -> "繁體中文"
{lang.system.chat_bot.language.answer_in} -> "繁體中文"

# Deterministic YAML mappings
mappings = {
    "Always answer in Traditional Chinese": "system.chat_bot.language.answer_in"
}
```

### Module Processing Methods

#### `_format_module_content(self, module_config: dict, module_name: str) -> str`

**Parameters:**
- `module_config`: Module configuration dictionary
- `module_name`: Name of the module

**Returns:**
- `str`: Formatted module content with title

**Processing Logic:**
- **Base Module**: Returns core instruction directly
- **List Values**: Converts to bullet points (`- item`)
- **String Values**: Appends directly
- **Dictionary Values**: Processes nested content recursively
- **Title Addition**: Adds appropriate module title if defined

#### `_process_nested_content(self, nested_config: dict, content_parts: List[str]) -> None`

**Parameters:**
- `nested_config`: Nested configuration dictionary
- `content_parts`: List to accumulate formatted content

**Description:**
Recursively processes nested configuration structures, handling lists, strings, and dictionaries at any depth level.

### Utility Methods

#### `apply_language_replacements(self, prompt: str, lang: str, lang_manager, mappings: Optional[dict] = None) -> str`

**Parameters:**
- `prompt`: Original prompt text
- `lang`: Language code (e.g., "zh_TW")
- `lang_manager`: LanguageManager instance
- `mappings`: Optional deterministic replacement mappings

**Returns:**
- `str`: Prompt with language placeholders resolved

**Features:**
- Supports both `{{lang.xxx}}` and `{lang.xxx}` patterns
- Automatic fallback path resolution (adds `system.` prefix)
- Handles complex language paths like `system.chat_bot.language.xxx`
- Deterministic YAML mapping replacements
- Safe error handling with original prompt fallback

#### `validate_module_references(self, config: dict, modules: List[str]) -> List[str]`

**Parameters:**
- `config`: Configuration dictionary
- `modules`: List of modules to validate

**Returns:**
- `List[str]`: List of missing module names

**Description:**
Validates that all requested modules exist in the configuration and returns any missing ones for debugging purposes.

#### `get_module_summary(self, config: dict, module_name: str) -> Optional[str]`

**Parameters:**
- `config`: Configuration dictionary
- `module_name`: Name of the module

**Returns:**
- `Optional[str]` Summary description or None if module doesn't exist

**Description:**
Provides debugging information about module configuration including item count and structure analysis.

#### `build_partial_prompt(self, config: dict, modules: List[str], max_length: Optional[int] = None) -> str`

**Parameters:**
- `config`: Configuration dictionary
- `modules`: List of modules
- `max_length`: Optional maximum length limit

**Returns:**
- `str`: Partial prompt content (truncated if necessary)

**Description:**
Creates a preview version of the prompt with optional length truncation for testing and debugging purposes.

## Integration

The PromptBuilder is the central component of the prompting system, used by:
- **PromptManager** for coordinated prompt operations
- **Orchestrator** for system prompt generation
- **Cache system** for precompiled template creation

## Dependencies

- `logging`: For debugging and monitoring
- `typing`: For type annotations
- `asyncio`: For async error reporting
- `function.func`: For error handling and reporting
- `re`: For regex pattern matching in language replacements

## Error Handling

All methods include comprehensive error handling:
- Errors are reported using `func.report_error()`
- Methods return safe fallback values on failure
- Detailed logging at debug and warning levels
- Graceful degradation for missing modules or variables