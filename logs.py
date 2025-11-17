# MIT License

# Copyright (c) 2024 starpig1129

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Enhanced logging system with guild-based organization.

This module provides structured logging capabilities with:
- Guild-based log organization (guild_{guild_id}/ structure)
- System-level logs for non-guild events
- Date-based log rotation with current file management
- Guild configuration management via JSON
- Performance monitoring and correlation ID tracking
"""

import logging
import os
import uuid
import sys
import re
import json
import gzip
import shutil
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

# Standard log format template as per specifications
LOG_FORMAT = (
    "[%(asctime)s] [%(levelname)s] [%(log_category)s] [%(custom_module)s] [%(function_name)s] "
    "[GUILD:%(guild_id)s] [USER:%(user_id)s] %(message)s"
)

# Format with additional context fields
ENHANCED_FORMAT = (
    "[%(asctime)s] [%(levelname)s] [%(log_category)s] [%(custom_module)s] [%(function_name)s] "
    "[GUILD:%(guild_id)s] [USER:%(user_id)s] [CID:%(correlation_id)s] "
    "%(message)s%(extra_context)s"
)


def apply_colors(text: str, enable_colored_logs: bool = True, level_colors: Optional[Dict[str, str]] = None, module_colors: Optional[Dict[str, str]] = None) -> str:
    """Apply colors to log text if enabled and supported.
    
    Args:
        text: Text to colorize
        enable_colored_logs: Whether to apply colors
        level_colors: Color mapping for log levels (from YAML config)
        module_colors: Color mapping for modules (from YAML config)
    """
    if not enable_colored_logs:
        return text
    
    # Default colors if not provided (fallback for backward compatibility)
    default_level_colors = {
        'DEBUG': '\033[90m',      # Gray
        'INFO': '\033[92m',       # Green
        'WARNING': '\033[93m',    # Yellow
        'ERROR': '\033[91m',      # Red
        'CRITICAL': '\033[95m',   # Magenta/Dark Red
        'RESET': '\033[0m'        # Reset color
    }
    
    default_module_colors = {
        'bot': '\033[94m',        # Blue
        'main': '\033[94m',
        'startup': '\033[94m',
        'cogs': '\033[96m',       # Cyan
        'utils': '\033[96m',
        'discord': '\033[95m',    # Magenta
        'sqlalchemy': '\033[95m',
        'httpx': '\033[95m',
        'web': '\033[93m',        # Orange/Yellow for web services
    }
    
    # Use provided colors or fall back to defaults
    COLORS = level_colors if level_colors else default_level_colors
    MODULE_COLORS = module_colors if module_colors else default_module_colors
    
    # Enhanced color detection with more permissive logic and debug output
    supports_color = (
        (hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()) or
        os.getenv('FORCE_COLOR', 'false').lower() == 'true' or
        os.getenv('ENABLE_CONSOLE_LOGGING', 'false').lower() == 'true' or
        sys.stderr.isatty() or  # Check stderr as well
        os.getenv('TERM', '').lower() in ['xterm', 'xterm-256color', 'screen', 'tmux']
    )
    
    if not supports_color:
        return text
    
    # Pre-clean any existing ANSI codes to prevent double-application
    # Remove any existing color codes to avoid duplication
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    text = ansi_escape.sub('', text)
    
    # Apply level-based coloring
    for level, color in COLORS.items():
        if level != 'RESET':
            # Use regex to match level patterns more precisely
            level_pattern = rf'\[({level})\]'
            replacement = f"{color}[{level}]{COLORS['RESET']}"
            text = re.sub(level_pattern, replacement, text)
    
    # Apply module-based coloring
    for module_prefix, color in MODULE_COLORS.items():
        # More precise regex to avoid false matches
        pattern = rf'\[([^\]]*{re.escape(module_prefix)}[^\]]*)\]'
        replacement = f"{color}[\\1]{COLORS['RESET']}"
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text


class ColoredConsoleHandler(logging.StreamHandler):
    """Colored console handler for structured logging with color support."""
    
    def __init__(self, enable_colored_logs: bool = True, simple_format: bool = True, config: Optional[Any] = None):
        super().__init__(sys.stdout)
        self.enable_colored_logs = enable_colored_logs
        self.simple_format = simple_format
        self.config = config
        
        # Choose format based on simple_format setting and configuration
        if simple_format:
            # Simple format: use from config or fallback
            simple_format_str = getattr(config, 'simple_format', "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s") if config else "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
            self.base_formatter = logging.Formatter(
                simple_format_str,
                datefmt='%H:%M:%S'
            )
        else:
            # Enhanced format with all details - use from config or fallback
            enhanced_format_str = getattr(config, 'enhanced_format', ENHANCED_FORMAT) if config else ENHANCED_FORMAT
            self.base_formatter = logging.Formatter(
                enhanced_format_str,
                datefmt='%H:%M:%S'
            )
        
        # Initialize colors for backward compatibility
        self._init_color_maps()
    
    def _init_color_maps(self):
        """Initialize color mappings for this handler."""
        # Get colors from config or use defaults
        if self.config:
            self.level_colors = getattr(self.config, 'level_colors', None)
            self.module_colors = getattr(self.config, 'module_colors', None)
        else:
            self.level_colors = None
            self.module_colors = None
    
    def emit(self, record):
        """Emit log record to console with color support."""
        try:
            # Set default values for missing structured fields to prevent formatting errors
            if not hasattr(record, 'log_category') or not getattr(record, 'log_category', None):
                record.log_category = "GENERAL"
            if not hasattr(record, 'custom_module') or not getattr(record, 'custom_module', None):
                record.custom_module = getattr(record, 'module_name', getattr(record, 'mod_name', record.name))
            if not hasattr(record, 'guild_id') or not getattr(record, 'guild_id', None):
                record.guild_id = "system"
            if not hasattr(record, 'user_id') or not getattr(record, 'user_id', None):
                record.user_id = "N/A"
            if not hasattr(record, 'correlation_id') or not getattr(record, 'correlation_id', None):
                record.correlation_id = getattr(record, 'correlation_id', "default")
            
            # Format base message using consistent formatter
            try:
                base_msg = self.base_formatter.format(record)
            except (KeyError, ValueError) as e:
                # Fallback to simple formatting if structured fields cause issues
                simple_format = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
                simple_formatter = logging.Formatter(simple_format, datefmt='%H:%M:%S')
                base_msg = simple_formatter.format(record)
            
            # Extract structured information for MESSAGE categories
            log_category = getattr(record, 'log_category', None)
            channel_name = getattr(record, 'channel_name', None)
            author_name = getattr(record, 'author_name', None)
            message_content = getattr(record, 'message_content', None)
            before_content = getattr(record, 'before_content', None)
            after_content = getattr(record, 'after_content', None)
            content_changed = getattr(record, 'content_changed', None)
            
            # Add structured context if available (for MESSAGE categories)
            msg = base_msg
            if log_category and 'MESSAGE' in log_category and any([channel_name, author_name, message_content, before_content, after_content]):
                context_parts = []
                if channel_name:
                    context_parts.append(f"CH:{channel_name}")
                if author_name:
                    context_parts.append(f"USER:{author_name}")
                
                # Handle MESSAGE_EDIT specifically
                if log_category == 'MESSAGE_EDIT':
                    if before_content is not None:
                        before_preview = before_content[:30] + "..." if len(before_content) > 30 else before_content
                        context_parts.append(f"BEFORE:{before_preview}")
                    if after_content is not None:
                        after_preview = after_content[:30] + "..." if len(after_content) > 30 else after_content
                        context_parts.append(f"AFTER:{after_preview}")
                    if content_changed is not None:
                        context_parts.append(f"CHANGED:{str(content_changed).upper()}")
                else:
                    # Regular MESSAGE categories
                    if message_content is not None:
                        # Truncate long messages for console display
                        content_preview = message_content[:50] + "..." if len(message_content) > 50 else message_content
                        context_parts.append(f"MSG:{content_preview}")
                
                if context_parts:
                    msg = f"{base_msg} [{' | '.join(context_parts)}]"
            
            # Apply colors if enabled - pass configured colors directly
            if self.enable_colored_logs and hasattr(self, 'level_colors') and hasattr(self, 'module_colors'):
                colored_msg = apply_colors(msg, True, self.level_colors, self.module_colors)
            else:
                colored_msg = msg
            
            # Write to stdout and flush
            try:
                sys.stdout.write(colored_msg + '\n')
                sys.stdout.flush()
            except (OSError, BrokenPipeError):
                # Handle broken pipe errors (e.g., when output is redirected)
                pass
            
        except Exception:
            self.handleError(record)


class GuildBasedRotatingFileHandler(logging.Handler):
    """Guild-based rotating file handler with date-based rotation.
    
    Implements guild-based log organization with:
    - Guild ID based directory structure
    - Date-based log rotation
    - Current log file management
    - Automatic compression of old logs
    - Guild configuration management
    """
    
    def __init__(self, guild_id: str, config: Optional[Any] = None):
        super().__init__()
        self.guild_id = guild_id
        self.config = config
        self.current_date = datetime.now().strftime('%Y%m%d')
        
        # Use config for log base dir or fallback to default
        self.log_base_dir = getattr(config, 'log_base_dir', 'logs') if config else 'logs'
        
        self.guild_log_dir = self._get_guild_log_dir()
        self._create_guild_directory()
        self._open_current_log_file()
        
        # Use config for format or fallback to default
        format_string = getattr(config, 'log_format', "[%(asctime)s] [%(levelname)s] [%(custom_module)s] %(message)s") if config else "[%(asctime)s] [%(levelname)s] [%(custom_module)s] %(message)s"
        
        # Structured formatter with consistent format and time format
        self.formatter = logging.Formatter(
            format_string,
            datefmt='%H:%M:%S'
        )
        
        # Initialize guild configuration manager
        self.config_manager = GuildConfigManager()

    def _get_guild_log_dir(self) -> str:
        """Get guild-specific log directory path."""
        if self.guild_id == 'system' or self.guild_id == 'N/A':
            return os.path.join(self.log_base_dir, 'system')
        else:
            return os.path.join(self.log_base_dir, f'guild_{self.guild_id}')

    def _create_guild_directory(self):
        """Create guild-specific log directory if it doesn't exist."""
        if not os.path.exists(self.guild_log_dir):
            os.makedirs(self.guild_log_dir)

    def _open_current_log_file(self):
        """Open current log file for writing."""
        current_log_path = os.path.join(self.guild_log_dir, 'bot_current.log')
        self.stream = open(current_log_path, 'a', encoding='utf-8')

    def _rotate_logs_if_needed(self):
        """Rotate logs when date changes."""
        current_date = datetime.now().strftime('%Y%m%d')
        
        if current_date != self.current_date:
            # Close current log file
            self.stream.close()
            
            # Rename current log to date-based log
            old_log_path = os.path.join(self.guild_log_dir, 'bot_current.log')
            new_log_path = os.path.join(self.guild_log_dir, f'bot_{self.current_date}.log')
            
            try:
                if os.path.exists(old_log_path):
                    shutil.move(old_log_path, new_log_path)
                    
                    # Compress the old log file
                    compressed_path = f"{new_log_path}.gz"
                    with open(new_log_path, 'rb') as f_in:
                        with gzip.open(compressed_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.remove(new_log_path)
                    
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning(f"Error rotating log file: {e}")
            
            # Open new current log file
            self._open_current_log_file()
            self.current_date = current_date
            
            # Clean up old log files (keep last 30 days)
            self._cleanup_old_logs()

    def _cleanup_old_logs(self):
        """Clean up log files older than 30 days."""
        try:
            cutoff_date = datetime.now().timestamp() - (30 * 24 * 60 * 60)  # 30 days ago
            
            for filename in os.listdir(self.guild_log_dir):
                if filename.startswith('bot_') and filename.endswith('.log.gz'):
                    file_path = os.path.join(self.guild_log_dir, filename)
                    if os.path.getmtime(file_path) < cutoff_date:
                        os.remove(file_path)
                        
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Error cleaning up old logs: {e}")

    def emit(self, record):
        """Emit log record with structured data."""
        try:
            # Check if log rotation is needed
            self._rotate_logs_if_needed()
            
            # Set default values for missing structured fields to prevent formatting errors
            if not hasattr(record, 'log_category') or not getattr(record, 'log_category', None):
                record.log_category = "GENERAL"
            if not hasattr(record, 'custom_module') or not getattr(record, 'custom_module', None):
                record.custom_module = getattr(record, 'module_name', getattr(record, 'mod_name', record.name))
            if not hasattr(record, 'guild_id') or not getattr(record, 'guild_id', None):
                record.guild_id = "system"
            if not hasattr(record, 'user_id') or not getattr(record, 'user_id', None):
                record.user_id = "N/A"
            if not hasattr(record, 'correlation_id') or not getattr(record, 'correlation_id', None):
                record.correlation_id = getattr(record, 'correlation_id', "default")
            
            # Format base message using consistent formatter
            try:
                if self.formatter:
                    base_msg = self.formatter.format(record)
                else:
                    base_msg = record.getMessage()
            except (KeyError, ValueError) as e:
                # Fallback to simple formatting if structured fields cause issues
                simple_format = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
                simple_formatter = logging.Formatter(simple_format, datefmt='%H:%M:%S')
                base_msg = simple_formatter.format(record)
            
            # Extract structured information for MESSAGE categories
            log_category = getattr(record, 'log_category', None)
            channel_name = getattr(record, 'channel_name', None)
            author_name = getattr(record, 'author_name', None)
            message_content = getattr(record, 'message_content', None)
            before_content = getattr(record, 'before_content', None)
            after_content = getattr(record, 'after_content', None)
            content_changed = getattr(record, 'content_changed', None)
            
            # Add structured context if available (for MESSAGE categories)
            msg = base_msg
            if log_category and 'MESSAGE' in log_category and any([channel_name, author_name, message_content, before_content, after_content]):
                context_parts = []
                if channel_name:
                    context_parts.append(f"CH:{channel_name}")
                if author_name:
                    context_parts.append(f"USER:{author_name}")
                
                # Handle MESSAGE_EDIT specifically
                if log_category == 'MESSAGE_EDIT':
                    if before_content is not None:
                        context_parts.append(f"BEFORE:{before_content}")
                    if after_content is not None:
                        context_parts.append(f"AFTER:{after_content}")
                    if content_changed is not None:
                        context_parts.append(f"CHANGED:{str(content_changed).upper()}")
                else:
                    # Regular MESSAGE categories
                    if message_content is not None:
                        context_parts.append(f"MSG:{message_content}")
                
                if context_parts:
                    msg = f"{base_msg} [{' | '.join(context_parts)}]"
            
            self.stream.write(msg + '\n')
            self.stream.flush()
            
            # Update guild configuration if this is a guild-related log
            guild_id = getattr(record, 'guild_id', None)
            if guild_id and guild_id != 'N/A' and guild_id != 'system':
                self.config_manager.update_guild_activity(guild_id)
            
        except Exception:
            self.handleError(record)

    def close(self):
        """Clean up guild-specific resources."""
        if hasattr(self, 'stream'):
            self.stream.close()
        super().close()


class GuildConfigManager:
    """Manages guild configuration and activity tracking."""
    
    def __init__(self, config_file: str = 'logs/guilds_and_channels.json'):
        self.config_file = config_file
        self.config_data = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load guild configuration from JSON file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Ensure the structure is correct
                    if 'guilds' not in data or not isinstance(data['guilds'], dict):
                        data['guilds'] = {}
                    if 'system' not in data:
                        data['system'] = {
                            'name': 'System',
                            'first_seen': datetime.now().isoformat(),
                            'last_activity': datetime.now().isoformat()
                        }
                    return data
            else:
                return {
                    'guilds': {},
                    'system': {
                        'name': 'System',
                        'first_seen': datetime.now().isoformat(),
                        'last_activity': datetime.now().isoformat()
                    }
                }
        except Exception:
            return {
                'guilds': {},
                'system': {
                    'name': 'System',
                    'first_seen': datetime.now().isoformat(),
                    'last_activity': datetime.now().isoformat()
                }
            }
    
    def _save_config(self):
        """Save guild configuration to JSON file."""
        try:
            # Ensure logs directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Error saving guild config: {e}")
    
    def update_guild_activity(self, guild_id: str, guild_name: Optional[str] = None):
        """Update guild activity information."""
        current_time = datetime.now().isoformat()
        
        if guild_id not in self.config_data['guilds']:
            self.config_data['guilds'][guild_id] = {
                'name': guild_name or f'Guild {guild_id}',
                'first_seen': current_time,
                'last_activity': current_time,
                'log_count': 0
            }
        else:
            self.config_data['guilds'][guild_id]['last_activity'] = current_time
            if guild_name:
                self.config_data['guilds'][guild_id]['name'] = guild_name
        
        self.config_data['guilds'][guild_id]['log_count'] += 1
        self._save_config()
    
    def get_guild_info(self, guild_id: str) -> Dict[str, Any]:
        """Get guild information."""
        return self.config_data['guilds'].get(guild_id, {})
    
    def get_all_guilds(self) -> Dict[str, Dict[str, Any]]:
        """Get all guilds information."""
        return self.config_data['guilds']
    
    def cleanup_inactive_guilds(self, days_threshold: int = 30):
        """Remove guilds that haven't been active for specified days."""
        current_time = datetime.now()
        cutoff_time = current_time.timestamp() - (days_threshold * 24 * 60 * 60)
        
        inactive_guilds = []
        for guild_id, guild_info in self.config_data['guilds'].items():
            last_activity = datetime.fromisoformat(guild_info['last_activity'])
            if last_activity.timestamp() < cutoff_time:
                inactive_guilds.append(guild_id)
        
        for guild_id in inactive_guilds:
            del self.config_data['guilds'][guild_id]
            # Remove guild log directory
            guild_dir = os.path.join('logs', f'guild_{guild_id}')
            if os.path.exists(guild_dir):
                shutil.rmtree(guild_dir)
        
        if inactive_guilds:
            self._save_config()


class GuildLoggerManager:
    """Manages loggers for multiple guilds with efficient resource management."""
    
    def __init__(self):
        self.loggers: Dict[str, logging.Logger] = {}
        self.handlers: Dict[str, GuildBasedRotatingFileHandler] = {}
        self.config_manager = GuildConfigManager()
    
    def get_logger(self, guild_id: str, guild_name: Optional[str] = None) -> logging.Logger:
        """Get or create a logger for the specified guild."""
        if guild_id in self.loggers:
            return self.loggers[guild_id]
        
        # Create new logger
        if guild_id == 'system' or guild_id == 'N/A':
            logger_name = 'system'
        else:
            logger_name = f'guild_{guild_id}'
        
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        
        # Clear existing handlers
        if logger.hasHandlers():
            logger.handlers.clear()
        
        # Create guild-based file handler
        handler = GuildBasedRotatingFileHandler(guild_id)
        logger.addHandler(handler)
        
        # Store references for cleanup
        self.loggers[guild_id] = logger
        self.handlers[guild_id] = handler
        
        # Update guild configuration
        if guild_id != 'system' and guild_id != 'N/A':
            self.config_manager.update_guild_activity(guild_id, guild_name)
        
        return logger
    
    def cleanup_inactive_loggers(self, hours_threshold: int = 24):
        """Clean up loggers that haven't been used recently."""
        current_time = datetime.now()
        
        inactive_guilds = []
        for guild_id, handler in self.handlers.items():
            # Check last modification time of the log directory
            guild_dir = handler._get_guild_log_dir()
            if os.path.exists(guild_dir):
                last_modified = datetime.fromtimestamp(os.path.getmtime(guild_dir))
                if (current_time - last_modified).total_seconds() > (hours_threshold * 3600):
                    inactive_guilds.append(guild_id)
        
        for guild_id in inactive_guilds:
            # Close and remove logger
            if guild_id in self.loggers:
                self.loggers[guild_id].handlers.clear()
                del self.loggers[guild_id]
            
            if guild_id in self.handlers:
                self.handlers[guild_id].close()
                del self.handlers[guild_id]
    
    def get_all_active_guilds(self) -> List[str]:
        """Get list of all currently active guilds."""
        return list(self.loggers.keys())
    
    def shutdown(self):
        """Shutdown all loggers and cleanup resources."""
        for handler in self.handlers.values():
            handler.close()
        
        self.loggers.clear()
        self.handlers.clear()


# Global guild logger manager instance
_guild_logger_manager = GuildLoggerManager()


def setup_enhanced_logger(guild_id: str,
                         guild_name: Optional[str] = None,
                         level: str = "INFO",
                         enable_colored_logs: bool = True) -> logging.Logger:
    """Setup logging system with guild-based organization and color support.
    
    Args:
        guild_id: Discord guild ID for log organization (use 'system' for system logs)
        guild_name: Discord guild name for configuration tracking
        level: Minimum log level
        enable_colored_logs: Enable colored console output
        
    Returns:
        Logger instance with guild-based structured logging
    """
    global _guild_logger_manager
    
    # Get guild-based logger
    logger = _guild_logger_manager.get_logger(guild_id, guild_name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Add console handler for development (only if environment variable set)
    if os.getenv('ENABLE_CONSOLE_LOGGING', 'false').lower() == 'true':
        # Check if console handler already exists
        has_console_handler = any(isinstance(h, ColoredConsoleHandler) for h in logger.handlers)
        
        if not has_console_handler:
            console_handler = ColoredConsoleHandler(enable_colored_logs, simple_format=True)
            logger.addHandler(console_handler)
    
    return logger


def get_system_logger() -> logging.Logger:
    """Get system-level logger for non-guild events."""
    return setup_enhanced_logger('system', 'System Logs')


def get_guild_logger(guild_id: str, guild_name: Optional[str] = None) -> logging.Logger:
    """Get guild-specific logger for Discord guild events."""
    return setup_enhanced_logger(guild_id, guild_name)


def cleanup_inactive_loggers(hours_threshold: int = 24):
    """Cleanup inactive guild loggers to save resources."""
    global _guild_logger_manager
    _guild_logger_manager.cleanup_inactive_loggers(hours_threshold)


def get_all_active_guilds() -> List[str]:
    """Get list of all currently active guilds."""
    global _guild_logger_manager
    return _guild_logger_manager.get_all_active_guilds()


def get_guild_config() -> GuildConfigManager:
    """Get guild configuration manager."""
    global _guild_logger_manager
    return _guild_logger_manager.config_manager


class StructuredRotatingFileHandler(GuildBasedRotatingFileHandler):
    pass

class TimedRotatingFileHandler(GuildBasedRotatingFileHandler):
    pass

class UnifiedLoggerManager:
    """Unified logging API manager providing centralized logging operations.
    
    This is the primary entry point for all logging operations, providing:
    - Consistent API across all logging functionality
    - YAML configuration-based setup
    - Guild-based logging organization
    - Backward compatibility with existing function names
    - Efficient resource management
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize UnifiedLoggerManager with YAML configuration.
        
        Args:
            config_path: Path to logging.yaml config file. If None, uses default.
        """
        self.logger = logging.getLogger(__name__)
        
        # Import LoggingConfig for centralized configuration management (lazy import)
        try:
            # Use lazy import to avoid potential circular dependency during module loading
            import importlib
            settings_module = importlib.import_module('addons.settings')
            LoggingConfig = getattr(settings_module, 'LoggingConfig', None)
            if LoggingConfig:
                self.config = LoggingConfig(config_path)
                self._use_yaml_config = True
            else:
                raise ImportError("LoggingConfig not available in addons.settings")
        except ImportError:
            # Fallback to basic configuration if LoggingConfig not available
            self.config = self._create_fallback_config()
            self._use_yaml_config = False
            self.logger.warning("LoggingConfig not available, using fallback configuration")
        
        # Initialize guild logger managers
        self.guild_managers: Dict[str, logging.Logger] = {}
        self.guild_config_managers: Dict[str, Any] = {}
        
        # Store configuration for backward compatibility
        self._setup_configuration()
        
        self.logger.debug("UnifiedLoggerManager initialized successfully")
    
    def _create_fallback_config(self):
        """Create fallback configuration when YAML config is not available."""
        class FallbackConfig:
            def __init__(self):
                self.enable_colored_logs = True
                self.level_colors = {
                    'DEBUG': '\033[90m', 'INFO': '\033[92m', 'WARNING': '\033[93m',
                    'ERROR': '\033[91m', 'CRITICAL': '\033[95m', 'RESET': '\033[0m'
                }
                self.module_colors = {
                    'bot': '\033[94m', 'main': '\033[94m', 'cogs': '\033[96m',
                    'utils': '\033[96m', 'discord': '\033[95m', 'sqlalchemy': '\033[95m'
                }
                self.log_format = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
                self.enhanced_format = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
                self.simple_format = "[%(levelname)s] %(message)s"
                self.log_base_dir = "logs"
                self.enable_console_logging = False
            
            def reload_configuration(self):
                """Fallback reload method that does nothing."""
                pass
            
            def cleanup(self):
                """Fallback cleanup method that does nothing."""
                pass
        return FallbackConfig()
    
    def _setup_configuration(self):
        """Setup configuration parameters for backward compatibility."""
        self.enable_colored_logs = getattr(self.config, 'enable_colored_logs', True)
        self.level_colors = getattr(self.config, 'level_colors', {})
        self.module_colors = getattr(self.config, 'module_colors', {})
        self.log_format = getattr(self.config, 'log_format', '')
        self.enhanced_format = getattr(self.config, 'enhanced_format', '')
        self.log_base_dir = getattr(self.config, 'log_base_dir', 'logs')
    
    def get_logger(self, 
                   guild_id: str, 
                   guild_name: Optional[str] = None,
                   level: str = "INFO") -> logging.Logger:
        """Get or create a logger for the specified guild.
        
        This is the primary unified API for getting loggers throughout the application.
        
        Args:
            guild_id: Discord guild ID for log organization (use 'system' for system logs)
            guild_name: Discord guild name for configuration tracking
            level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            
        Returns:
            Logger instance with structured logging capabilities
        """
        if guild_id in self.guild_managers:
            logger = self.guild_managers[guild_id]
            logger.setLevel(getattr(logging, level.upper()))
            return logger
        
        # Create new guild-based logger
        logger = self._create_guild_logger(guild_id, guild_name, level)
        
        # Store reference for resource management
        self.guild_managers[guild_id] = logger
        
        # Update guild configuration if not system
        if guild_id not in ['system', 'N/A']:
            self._update_guild_config(guild_id, guild_name)
        
        return logger
    
    def _create_guild_logger(self, guild_id: str, guild_name: Optional[str], level: str) -> logging.Logger:
        """Create a new guild-specific logger."""
        # Use existing logger creation logic but integrate with YAML config
        guild_log_dir = self._get_guild_log_dir(guild_id)
        
        # Create logger name
        if guild_id in ['system', 'N/A']:
            logger_name = 'system'
        else:
            logger_name = f'guild_{guild_id}'
        
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level.upper()))
        
        # Clear existing handlers
        if logger.hasHandlers():
            logger.handlers.clear()
        
        # Create guild-based file handler with YAML configuration
        handler = GuildBasedRotatingFileHandler(guild_id, self.config)
        logger.addHandler(handler)
        
        # Add console handler if enabled and configured
        if self._should_add_console_handler():
            console_handler = ColoredConsoleHandler(self.enable_colored_logs, simple_format=True, config=self.config)
            logger.addHandler(console_handler)
        
        return logger
    
    def _get_guild_log_dir(self, guild_id: str) -> str:
        """Get guild-specific log directory path using YAML configuration."""
        if guild_id in ['system', 'N/A']:
            return os.path.join(self.log_base_dir, 'system')
        else:
            return os.path.join(self.log_base_dir, f'guild_{guild_id}')
    
    def _should_add_console_handler(self) -> bool:
        """Check if console handler should be added based on configuration."""
        # Always enable console logging for debugging unless explicitly disabled
        enable_console = getattr(self.config, 'enable_console_logging', True)  # Default to True
        env_override = os.getenv('ENABLE_CONSOLE_LOGGING', 'false').lower() == 'true'
        
        # Environment variable takes precedence
        if env_override:
            return True
        
        # Return configuration setting (now defaults to True for development)
        return enable_console
    
    def _update_guild_config(self, guild_id: str, guild_name: Optional[str]):
        """Update guild configuration tracking."""
        if guild_id not in self.guild_config_managers:
            self.guild_config_managers[guild_id] = GuildConfigManager()
        
        self.guild_config_managers[guild_id].update_guild_activity(guild_id, guild_name)
    
    def setup_enhanced_logger(self, 
                             guild_id: str,
                             guild_name: Optional[str] = None,
                             level: str = "INFO",
                             enable_colored_logs: Optional[bool] = None) -> logging.Logger:
        """Setup enhanced logger with guild-based organization and color support.
        
        Args:
            guild_id: Discord guild ID for log organization
            guild_name: Discord guild name for configuration tracking
            level: Minimum log level
            enable_colored_logs: Override colored console output setting
            
        Returns:
            Logger instance with enhanced structured logging
        """
        # Use provided colored logs setting or fall back to config
        colored_logs = enable_colored_logs if enable_colored_logs is not None else self.enable_colored_logs
        
        # Get or create guild logger
        logger = self.get_logger(guild_id, guild_name, level)
        
        # Update colored logs setting if needed
        if colored_logs != self.enable_colored_logs:
            for handler in logger.handlers:
                if isinstance(handler, ColoredConsoleHandler):
                    handler.enable_colored_logs = colored_logs
        
        self.logger.debug(f"Enhanced logger setup completed for guild: {guild_id}")
        return logger
    
    def get_system_logger(self) -> logging.Logger:
        """Get system-level logger for non-guild events."""
        return self.get_logger('system', 'System Logs')
    
    def get_guild_logger(self, guild_id: str, guild_name: Optional[str] = None) -> logging.Logger:
        """Get guild-specific logger for Discord guild events."""
        return self.get_logger(guild_id, guild_name)
    
    def cleanup_inactive_loggers(self, hours_threshold: int = 24):
        """Cleanup inactive guild loggers to save resources."""
        current_time = datetime.now()
        inactive_guilds = []
        
        for guild_id, logger in self.guild_managers.items():
            if guild_id in ['system', 'N/A']:
                continue
                
            # Check if logger has been inactive
            # For simplicity, we'll check if no handlers are present or log directory is old
            if not logger.handlers:
                inactive_guilds.append(guild_id)
                continue
            
            # Check log directory modification time
            guild_log_dir = self._get_guild_log_dir(guild_id)
            if os.path.exists(guild_log_dir):
                last_modified = datetime.fromtimestamp(os.path.getmtime(guild_log_dir))
                if (current_time - last_modified).total_seconds() > (hours_threshold * 3600):
                    inactive_guilds.append(guild_id)
        
        # Clean up inactive loggers
        for guild_id in inactive_guilds:
            if guild_id in self.guild_managers:
                logger = self.guild_managers[guild_id]
                logger.handlers.clear()
                del self.guild_managers[guild_id]
            
            if guild_id in self.guild_config_managers:
                del self.guild_config_managers[guild_id]
        
        if inactive_guilds:
            self.logger.debug(f"Cleaned up {len(inactive_guilds)} inactive guild loggers")
    
    def get_all_active_guilds(self) -> List[str]:
        """Get list of all currently active guilds."""
        return [guild_id for guild_id in self.guild_managers.keys() if guild_id not in ['system', 'N/A']]
    
    def get_configuration_summary(self) -> Dict[str, Any]:
        """Get summary of current logging configuration."""
        return {
            "yaml_config_available": self._use_yaml_config,
            "active_guilds": len(self.get_all_active_guilds()),
            "colored_logs_enabled": self.enable_colored_logs,
            "config_source": "yaml" if self._use_yaml_config else "fallback",
            "log_base_dir": self.log_base_dir
        }
    
    def reload_configuration(self):
        """Reload configuration from YAML file."""
        if self._use_yaml_config and hasattr(self.config, 'reload_configuration'):
            self.config.reload_configuration()
            self._setup_configuration()
            self.logger.info("Logging configuration reloaded successfully")
        else:
            self.logger.warning("Configuration reload not available")
    
    def shutdown(self):
        """Shutdown all loggers and cleanup resources."""
        for logger in self.guild_managers.values():
            logger.handlers.clear()
        
        self.guild_managers.clear()
        self.guild_config_managers.clear()
        
        if hasattr(self.config, 'cleanup'):
            self.config.cleanup()
        
        self.logger.info("UnifiedLoggerManager shutdown completed")
    
    def setup_root_logger(self):
        """Setup root logger with appropriate handlers and level."""
        import logging
        
        root_logger = logging.getLogger()
        
        # Set root logger level based on configuration
        root_level = getattr(self.config, 'root_logger_level', 'INFO')
        root_logger.setLevel(getattr(logging, root_level.upper()))
        
        # This prevents duplicate output when ColoredConsoleHandler is already handling console logging
        has_colored_console = any(
            isinstance(handler, ColoredConsoleHandler)
            for handler in root_logger.handlers
        ) or (
            # Also check if any guild loggers have ColoredConsoleHandler
            hasattr(self, 'guild_managers') and any(
                isinstance(h, ColoredConsoleHandler)
                for logger in self.guild_managers.values()
                for h in logger.handlers
            )
        )
        
        if not has_colored_console and self._should_add_console_handler():
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)
            
            # Use simple format for root logger
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
            
            self.logger.debug("Root logger console handler added")
        
        # Ensure propagation is enabled for proper logging hierarchy
        root_logger.propagate = True
        
        self.logger.debug(f"Root logger setup completed - level: {root_logger.level}, handlers: {len(root_logger.handlers)}")
    
    def initialize_logging_system(self):
        """Initialize the complete logging system including root logger."""
        self.setup_root_logger()
        
        # Setup system logger as well
        system_logger = self.get_system_logger()
        
        self.logger.info("Complete logging system initialized successfully")
        return system_logger


# Global unified logger manager instance
_unified_logger_manager = None


def get_unified_logger_manager(config_path: Optional[str] = None) -> UnifiedLoggerManager:
    """Get or create the global unified logger manager instance.
    
    Args:
        config_path: Path to logging.yaml config file
        
    Returns:
        UnifiedLoggerManager instance
    """
    global _unified_logger_manager
    
    if _unified_logger_manager is None:
        _unified_logger_manager = UnifiedLoggerManager(config_path)
    
    return _unified_logger_manager


# Legacy compatibility - DEPRECATED
__all__ = [
    "UnifiedLoggerManager",
    "GuildBasedRotatingFileHandler",
    "ColoredConsoleHandler",
    "GuildConfigManager",
    "StructuredRotatingFileHandler",
    "TimedRotatingFileHandler",
    "get_unified_logger_manager",
    "apply_colors",
]