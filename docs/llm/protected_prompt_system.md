# Protected Prompt System

## Overview

The `llm/prompting/protected_prompt_manager.py` module implements a robust, two-tier prompt management system. It ensures that critical system instructions (like Discord formatting and memory handling) remain immutable while allowing for user-level customization of personality and tone.

## Two-Tier Architecture

The system categorizes prompt modules into two distinct types:

### 1. Protected Modules (`PROTECTED_MODULES`)
These modules are essential for the bot's core functionality. They are **always** loaded from the base configuration files (e.g., `base_configs/prompt/message_agent.yaml`) and cannot be overridden by users or external database configs.

- **`output_format`**: Discord formatting rules and parsing markers (`<som>`, `<eom>`).
- **`input_parsing`**: Logic for understanding message formats and speaker identification.
- **`memory_system`**: Instructions on how to utilize procedural and short-term memory.
- **`information_handling`**: Priority logic for resolving conflicting information.
- **`error_handling`**: Standardized error response behaviors.
- **`reminders`**: Final, critical "sanity check" instructions.

### 2. Customizable Modules (`CUSTOMIZABLE_MODULES`)
These modules define the "soul" of the bot and can be safely overridden at the server or user level.

- **`identity`**: Bot name, creator, and general role.
- **`response_principles`**: Tone, style, and language preferences.
- **`interaction`**: Engagement style and conversational hooks.
- **`professional_personality`**: Alternative high-precision mode.

## Core Features

- **Composition Engine**: Dynamically assembles a complete system prompt by joining modules in a specified order.
- **Immutability Enforcement**: Explicitly prevents `set_custom_module` from modifying protected keys.
- **Instance Caching**: Uses a global instance cache (`_protected_manager_instances`) to ensure configuration is loaded efficiently across different components.
- **Variable Support**: Provides base variables like `{bot_name}`, `{creator}`, and `{environment}` for injection into templates.

## Usage

### Getting the Manager

```python
from llm.prompting.protected_prompt_manager import get_protected_prompt_manager

manager = get_protected_prompt_manager()
```

### Composing a Prompt

```python
# Compose with base modules
system_prompt = manager.compose_system_prompt()

# Compose with custom overrides for specific modules
custom_overrides = {"identity": "You are a grumpy cat assistant."}
personalized_prompt = manager.compose_system_prompt(custom_module_contents=custom_overrides)
```

## Configuration Schema

The system expects YAML files with the following structure:

```yaml
base:
  bot_name: "🐖🐖"
  creator: "StarPig"

composition:
  module_order:
    - identity
    - memory_system
    - output_format

output_format:
  description: "Critical formatting rules"
  content: "Always wrap your core reply in <som> and <eom> tags..."

identity:
  description: "Bot identity"
  content: "You are {bot_name}, a helpful agent..."
```

---
*The Protected Prompt System is the primary defense against "prompt injection" or accidental misconfiguration that could break the bot's parsing logic.*
