"""
Protected Prompt Management System.

This module implements a two-tier prompt system:
1. System-level prompts (protected, from base_configs)
2. User-customizable prompts (can be overridden)

The system ensures critical prompts like Discord format instructions,
context handling, and input parsing cannot be accidentally modified by users.
"""

from typing import Dict, List, Optional, Set
from pathlib import Path
import yaml

from addons.logging import get_logger
from addons.settings import prompt_config

_logger = get_logger(server_id="Bot", source="llm.prompting.protected_prompt_manager")


class ProtectedPromptManager:
    """
    Manages system-level (protected) and user-customizable prompts.
    
    Protected modules are always loaded from base_configs and cannot be overridden.
    User-customizable modules can be modified through database or custom configs.
    """
    
    # Define which modules are system-protected (cannot be modified by users)
    PROTECTED_MODULES: Set[str] = {
        "output_format",           # Discord format rules, critical for parsing
        "input_parsing",           # Message format understanding, speaker identification
        "memory_system",           # How to use procedural/short-term memory
        "information_handling",    # Priority order for information sources
        "error_handling",          # How to handle errors
        "reminders",               # Final critical reminders
    }
    
    # Define which modules users can customize
    CUSTOMIZABLE_MODULES: Set[str] = {
        "identity",                # Bot name, creator, role
        "response_principles",     # Tone, style, language preferences
        "interaction",             # Engagement style
        "professional_personality" # Alternative personality mode
    }
    
    def __init__(self, base_config_path: Optional[str] = None):
        """
        Initialize the protected prompt manager.
        
        Args:
            base_config_path: Path to base config YAML file.
                             Defaults to message_agent.yaml in base_configs/prompt/
        """
        if base_config_path is None:
            base_config_path = f"{prompt_config.path}/message_agent.yaml"
        
        self.base_config_path = Path(base_config_path)
        self.base_config: Dict = {}
        self.custom_modules: Dict[str, str] = {}
        
        self._load_base_config()
    
    def _load_base_config(self) -> None:
        """Load base configuration from YAML file."""
        try:
            with open(self.base_config_path, 'r', encoding='utf-8') as f:
                self.base_config = yaml.safe_load(f)
            _logger.info(f"Loaded base config from {self.base_config_path}")
        except Exception as e:
            _logger.error(f"Failed to load base config: {e}", exception=e)
            self.base_config = {}
    
    def get_protected_module(self, module_name: str) -> Optional[str]:
        """
        Get a protected module's content.
        
        Protected modules are ALWAYS loaded from base_configs and cannot be overridden.
        
        Args:
            module_name: Name of the module
            
        Returns:
            Module content string, or None if not found
        """
        if module_name not in self.PROTECTED_MODULES:
            _logger.warning(
                f"Module '{module_name}' is not in protected list. "
                f"Use get_customizable_module() instead."
            )
            return None
        
        try:
            module_data = self.base_config.get(module_name, {})
            if isinstance(module_data, dict):
                return module_data.get('content', '')
            return str(module_data)
        except Exception as e:
            _logger.error(
                f"Failed to get protected module '{module_name}': {e}",
                exception=e
            )
            return None
    
    def get_customizable_module(
        self, 
        module_name: str, 
        custom_content: Optional[str] = None
    ) -> Optional[str]:
        """
        Get a customizable module's content.
        
        If custom_content is provided, it overrides the base config.
        Otherwise, returns the base config content.
        
        Args:
            module_name: Name of the module
            custom_content: Optional custom content to override base
            
        Returns:
            Module content string, or None if not found
        """
        if module_name not in self.CUSTOMIZABLE_MODULES:
            _logger.warning(
                f"Module '{module_name}' is not in customizable list. "
                f"Protected modules cannot be customized."
            )
            return None
        
        # If custom content is provided, use it
        if custom_content:
            _logger.debug(f"Using custom content for module '{module_name}'")
            return custom_content
        
        # If custom module exists in cache, use it
        if module_name in self.custom_modules:
            _logger.debug(f"Using cached custom module '{module_name}'")
            return self.custom_modules[module_name]
        
        # Fall back to base config
        try:
            module_data = self.base_config.get(module_name, {})
            if isinstance(module_data, dict):
                return module_data.get('content', '')
            return str(module_data)
        except Exception as e:
            _logger.error(
                f"Failed to get customizable module '{module_name}': {e}",
                exception=e
            )
            return None
    
    def set_custom_module(self, module_name: str, content: str) -> bool:
        """
        Set custom content for a customizable module.
        
        Args:
            module_name: Name of the module
            content: Custom content
            
        Returns:
            True if successful, False if module is protected or error occurred
        """
        if module_name in self.PROTECTED_MODULES:
            _logger.warning(
                f"Cannot customize protected module '{module_name}'. "
                f"Protected modules: {self.PROTECTED_MODULES}"
            )
            return False
        
        if module_name not in self.CUSTOMIZABLE_MODULES:
            _logger.warning(
                f"Module '{module_name}' is not in customizable list. "
                f"Customizable modules: {self.CUSTOMIZABLE_MODULES}"
            )
            return False
        
        try:
            self.custom_modules[module_name] = content
            _logger.info(f"Set custom content for module '{module_name}'")
            return True
        except Exception as e:
            _logger.error(f"Failed to set custom module '{module_name}': {e}", exception=e)
            return False
    
    def compose_system_prompt(
        self,
        module_order: Optional[List[str]] = None,
        custom_module_contents: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Compose complete system prompt from modules.
        
        Protected modules are always loaded from base_configs.
        Customizable modules can be overridden through custom_module_contents.
        
        Args:
            module_order: List of module names in desired order.
                         Defaults to composition.module_order from base config.
            custom_module_contents: Dict mapping module names to custom content.
                                   Only works for customizable modules.
        
        Returns:
            Complete system prompt string
        """
        if module_order is None:
            composition = self.base_config.get('composition', {})
            module_order = composition.get('module_order', composition.get('default_modules', []))
        
        prompt_parts: List[str] = []
        custom_contents = custom_module_contents or {}
        
        for module_name in module_order:
            content = None
            
            # Always use protected version for protected modules
            if module_name in self.PROTECTED_MODULES:
                content = self.get_protected_module(module_name)
                if content:
                    _logger.debug(f"Added protected module: {module_name}")
            
            # Allow customization for customizable modules
            elif module_name in self.CUSTOMIZABLE_MODULES:
                custom_content = custom_contents.get(module_name)
                content = self.get_customizable_module(module_name, custom_content)
                if content:
                    source = "custom" if custom_content else "base"
                    _logger.debug(f"Added customizable module: {module_name} (source: {source})")
            
            # Unknown module - try to load from base config anyway
            else:
                _logger.warning(f"Unknown module '{module_name}', attempting to load from base config")
                module_data = self.base_config.get(module_name, {})
                if isinstance(module_data, dict):
                    content = module_data.get('content', '')
                else:
                    content = str(module_data) if module_data else None
            
            if content and content.strip():
                prompt_parts.append(content.strip())
        
        return "\n\n".join(prompt_parts)
    
    def get_base_variables(self) -> Dict[str, str]:
        """
        Get base configuration variables (bot_name, creator, etc.).
        
        Returns:
            Dict of base variables
        """
        base = self.base_config.get('base', {})
        return {
            'bot_name': base.get('bot_name', '🐖🐖'),
            'creator': base.get('creator', '星豬'),
            'environment': base.get('environment', 'Discord server'),
        }
    
    def is_module_protected(self, module_name: str) -> bool:
        """Check if a module is protected (cannot be modified)."""
        return module_name in self.PROTECTED_MODULES
    
    def is_module_customizable(self, module_name: str) -> bool:
        """Check if a module is customizable."""
        return module_name in self.CUSTOMIZABLE_MODULES
    
    def get_module_info(self) -> Dict[str, any]:
        """
        Get information about available modules.
        
        Returns:
            Dict containing module categorization and descriptions
        """
        return {
            'protected_modules': list(self.PROTECTED_MODULES),
            'customizable_modules': list(self.CUSTOMIZABLE_MODULES),
            'module_descriptions': {
                name: data.get('description', '') 
                for name, data in self.base_config.items()
                if isinstance(data, dict) and 'description' in data
            }
        }


# Global instance cache
_protected_manager_instances: Dict[str, ProtectedPromptManager] = {}


def get_protected_prompt_manager(
    config_path: Optional[str] = None
) -> ProtectedPromptManager:
    """
    Get or create a ProtectedPromptManager instance.
    
    Args:
        config_path: Path to base config file.
                    Defaults to message_agent.yaml in base_configs/prompt/
    
    Returns:
        ProtectedPromptManager instance
    """
    if config_path is None:
        config_path = f"{prompt_config.path}/message_agent.yaml"
    
    if config_path not in _protected_manager_instances:
        _protected_manager_instances[config_path] = ProtectedPromptManager(config_path)
        _logger.info(f"Created new ProtectedPromptManager for {config_path}")
    
    return _protected_manager_instances[config_path]
