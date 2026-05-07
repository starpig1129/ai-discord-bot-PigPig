# File: `llm/prompting/protected_prompt_manager.py`

## Overview
Protected Prompt Management System. This file is part of the llm subsystem and handles the primary operations for its respective domain.

## Classes

### `ProtectedPromptManager`
Manages system-level (protected) and user-customizable prompts.

- **Attributes**:
  - `PROTECTED_MODULES` (`Set[str]`): Class attribute.
  - `CUSTOMIZABLE_MODULES` (`Set[str]`): Class attribute.
  - `base_config_path` (`Any`): Instance attribute.
  - `base_config` (`Dict`): Instance attribute.
  - `custom_modules` (`Dict[Tuple[str, str]]`): Instance attribute.

- **Methods**:
  - `__init__(base_config_path: Optional[str]) -> Any`: Initialize the protected prompt manager.
  - `_load_base_config() -> None`: Load base configuration from YAML file.
  - `get_protected_module(module_name: str) -> Optional[str]`: Get a protected module's content.
  - `get_customizable_module(module_name: str, custom_content: Optional[str]) -> Optional[str]`: Get a customizable module's content.
  - `set_custom_module(module_name: str, content: str) -> bool`: Set custom content for a customizable module.
  - `compose_system_prompt(module_order: Optional[List[str]], custom_module_contents: Optional[Dict[Tuple[str, str]]]) -> str`: Compose complete system prompt from modules.
  - `get_base_variables() -> Dict[Tuple[str, str]]`: Get base configuration variables (bot_name, creator, etc.).
  - `is_module_protected(module_name: str) -> bool`: Check if a module is protected (cannot be modified).
  - `is_module_customizable(module_name: str) -> bool`: Check if a module is customizable.
  - `get_module_info() -> Dict[Tuple[str, any]]`: Get information about available modules.

## Functions

### `get_protected_prompt_manager(config_path: Optional[str]) -> ProtectedPromptManager`
Get or create a ProtectedPromptManager instance. Plays a key role in the system logic.
