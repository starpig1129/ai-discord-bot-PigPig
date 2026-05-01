# Protected Prompt Management System

## Overview

This system implements a **dual-layer prompt management architecture**, ensuring that critical system-level prompts are not accidentally modified by users while allowing users to customize personalized bot behaviors.

## Architecture Design

### Two-Layer Prompt Classification

#### 1. **Protected Modules** ❌ Read-Only

These modules contain critical instructions for system operation and **must never be modified by users**:

- **`output_format`**: Discord formatting rules (`<som>` `<eom>` tags, timestamp formats, mention formats, etc.)
- **`input_parsing`**: Message format understanding, speaker identification, pronoun rules
- **`memory_system`**: Guidelines for using Procedural Memory and Short-term Memory
- **`information_handling`**: Priority of information sources
- **`error_handling`**: Error handling guidelines
- **`reminders`**: Final critical reminders

**Why must these be protected?**
- Modifying Output Format could break the bot's response parsing
- Modifying Input Parsing could lead to misunderstanding multi-user conversations
- Modifying Memory System could disrupt the bot's ability to use context memory correctly

#### 2. **Customizable Modules** ✅ User-Editable

These modules allow users to customize the bot's personality and behavior:

- **`identity`**: Bot name, creator, role definition
- **`response_principles`**: Tone, style, language preferences, response length
- **`interaction`**: Interaction style, engagement levels
- **`professional_personality`**: Personality settings for professional mode

**What can users customize?**
- Bot's name and role
- Conversational tone (humorous/formal/friendly, etc.)
- Response style and length preferences
- Language and wording habits

## Usage

### Implementation in Orchestrator

```python
from llm.prompting.protected_prompt_manager import get_protected_prompt_manager

# Get Protected Prompt Manager
protected_manager = get_protected_prompt_manager()

# Compose system prompt
# Protected modules are always loaded from base_configs
# Customizable modules can be overridden via custom_module_contents
system_prompt = protected_manager.compose_system_prompt(
    custom_module_contents={
        'identity': 'Custom identity description',  # ✅ Allowed
        'output_format': 'Custom format'           # ❌ Ignored, uses base_configs version
    }
)
```

### Checking Module Status

```python
# Check if a module is protected
protected_manager.is_module_protected('output_format')  # True
protected_manager.is_module_customizable('identity')    # True

# Get module information
info = protected_manager.get_module_info()
# {
#     'protected_modules': ['output_format', 'input_parsing', ...],
#     'customizable_modules': ['identity', 'response_principles', ...],
#     'module_descriptions': {...}
# }
```

### Setting Custom Modules

```python
# Only customizable modules can be set
success = protected_manager.set_custom_module('identity', 'I am a friendly assistant')
# Returns True

# Attempting to set a protected module will fail
success = protected_manager.set_custom_module('output_format', 'Custom Format')
# Returns False and logs a warning
```

## Data Flow

```
User Request → Orchestrator
                    ↓
          _build_message_agent_prompt()
                    ↓
          ProtectedPromptManager
                    ↓
    ┌───────────────┴────────────────┐
    │                                │
Protected Modules          Customizable Modules
(base_configs ONLY)      (base_configs + custom overrides)
    │                                │
    └───────────────┬────────────────┘
                    ↓
          compose_system_prompt()
                    ↓
          Complete System Prompt
          (with variable replacements)
                    ↓
            Message Agent
```

## Security Guarantees

1. **Protected Modules always load from base_configs**
   - Overrides in database or settings are ignored
   - Ensures critical system instructions remain intact

2. **Explicit Module Classification**
   - `PROTECTED_MODULES` and `CUSTOMIZABLE_MODULES` are explicitly defined in code
   - Any new modules must be explicitly categorized

3. **Logging and Error Reporting**
   - All attempts to modify protected modules are logged
   - Clear error messages guide proper usage

## Future Roadmap

### Phase 1 (Current) ✅
- Implemented basic protected/customizable module separation
- Integrated ProtectedPromptManager in Orchestrator
- Provided protection for message_agent

### Phase 2 (Planned)
- Implement protection mechanism for info_agent
- Implement custom module storage at the database level
- Provide Discord commands for users to manage custom modules

### Phase 3 (Planned)
- Implement module version control
- Provide module templates and default presets
- Finer-grained permission control (server-level, channel-level)

## Example Scenarios

### Scenario 1: User wants to change the bot's name

```python
# ✅ Allowed: identity is a customizable module
protected_manager.set_custom_module('identity', """
## Bot Identity
- Name: Super Assistant <@{bot_id}>
- Creator: {creator} <@{bot_owner_id}>
- Platform: {environment}
- Role: Professional technical support assistant
""")
```

### Scenario 2: User tries to modify the output format

```python
# ❌ Denied: output_format is a protected module
result = protected_manager.set_custom_module('output_format', """
## Custom Output Format
- Use [bot]: prefix instead of <som><eom> tags
""")
# result = False
# Log: Cannot customize protected module 'output_format'
```

### Scenario 3: Composing a prompt with custom modules

```python
custom_modules = {
    'identity': 'Custom Identity',
    'response_principles': 'Custom Response Principles'
}

prompt = protected_manager.compose_system_prompt(
    custom_module_contents=custom_modules
)

# Result:
# - identity, response_principles use custom content
# - output_format, input_parsing, and other protected modules use base_configs
```

## Troubleshooting

### Q: Why isn't my custom prompt taking effect?

A: Check if the module you are trying to customize is protected. Use `is_module_protected()` to verify.

### Q: How do I know which modules are customizable?

A: Use the `get_module_info()` method to view all module classifications.

### Q: Will protected modules update with new versions?

A: Yes, protected modules will update alongside base_configs updates, ensuring system functionality remains optimal.

## Related Files

- `llm/prompting/protected_prompt_manager.py` - Protection system implementation
- `llm/orchestrator.py` - Usage in Orchestrator
- `base_configs/prompt/message_agent.yaml` - Base configuration (contains all modules)
- `base_configs/prompt/info_agent.yaml` - Info Agent configuration

## Conclusion

The Protected Prompt Management System provides a balanced solution:

✅ **Protects System Integrity**: Critical Discord formatting and context handling instructions are safeguarded
✅ **Allows Personalization**: Users can still customize the bot's personality and behavior
✅ **Clear Boundaries**: Explicit distinction between what can and cannot be changed
✅ **Backward Compatibility**: Existing get_system_prompt remains available as a fallback
