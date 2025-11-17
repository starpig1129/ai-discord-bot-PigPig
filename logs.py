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


def apply_colors(text: str, enable_colored_logs: bool = True) -> str:
    """Apply colors to log text if enabled and supported."""
    if not enable_colored_logs:
        return text
    
    # Color codes for different log levels
    COLORS = {
        'DEBUG': '\033[90m',      # Gray
        'INFO': '\033[92m',       # Green
        'WARNING': '\033[93m',    # Yellow
        'ERROR': '\033[91m',      # Red
        'CRITICAL': '\033[95m',   # Magenta/Dark Red
        'RESET': '\033[0m'        # Reset color
    }
    
    # Color codes for different modules
    MODULE_COLORS = {
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
    
    # Detect if output supports colors
    supports_color = (hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()) or \
                     os.getenv('FORCE_COLOR', 'false').lower() == 'true'
    
    if not supports_color:
        return text
    
    # Apply level-based coloring
    for level, color in COLORS.items():
        if level != 'RESET':
            text = text.replace(f"[{level}]", f"{color}[{level}]{COLORS['RESET']}")
    
    # Apply module-based coloring
    for module_prefix, color in MODULE_COLORS.items():
        pattern = rf'\[([^\]]*{re.escape(module_prefix)}[^\]]*)\]'
        text = re.sub(pattern, f"{color}[\\1]{COLORS['RESET']}", text, flags=re.IGNORECASE)
    
    return text


class ColoredConsoleHandler(logging.StreamHandler):
    """Colored console handler for structured logging with color support."""
    
    def __init__(self, enable_colored_logs: bool = True, simple_format: bool = True):
        super().__init__(sys.stdout)
        self.enable_colored_logs = enable_colored_logs
        self.simple_format = simple_format
        
        # Choose format based on simple_format setting
        if simple_format:
            # Simple format: [TIME] [LEVEL] [MODULE] message
            self.base_formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                datefmt='%H:%M:%S'
            )
        else:
            # Enhanced format with all details
            self.base_formatter = logging.Formatter(
                ENHANCED_FORMAT,
                datefmt='%H:%M:%S'
            )
    
    def emit(self, record):
        """Emit log record to console with color support."""
        try:
            # Set custom_module for consistent formatting
            if not hasattr(record, 'custom_module') or not getattr(record, 'custom_module', None):
                record.custom_module = getattr(record, 'module_name', getattr(record, 'mod_name', record.name))
            
            # Format base message using consistent formatter
            base_msg = self.base_formatter.format(record)
            
            # Extract structured information for MESSAGE categories
            log_category = getattr(record, 'log_category', getattr(record, 'category', None))
            channel_name = getattr(record, 'channel_name', None)
            author_name = getattr(record, 'author_name', None)
            message_content = getattr(record, 'message_content', None)
            
            # Add structured context if available (for MESSAGE categories)
            msg = base_msg
            if log_category and 'MESSAGE' in log_category and any([channel_name, author_name, message_content]):
                context_parts = []
                if channel_name:
                    context_parts.append(f"CH:{channel_name}")
                if author_name:
                    context_parts.append(f"USER:{author_name}")
                if message_content is not None:
                    # Truncate long messages for console display
                    content_preview = message_content[:50] + "..." if len(message_content) > 50 else message_content
                    context_parts.append(f"MSG:{content_preview}")
                
                if context_parts:
                    msg = f"{base_msg} [{' | '.join(context_parts)}]"
            
            # Apply colors if enabled
            colored_msg = apply_colors(msg, self.enable_colored_logs)
            
            # Print message
            print(colored_msg)
            
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
    
    def __init__(self, guild_id: str):
        super().__init__()
        self.guild_id = guild_id
        self.current_date = datetime.now().strftime('%Y%m%d')
        self.log_base_dir = 'logs'
        self.guild_log_dir = self._get_guild_log_dir()
        self._create_guild_directory()
        self._open_current_log_file()
        
        # Structured formatter with consistent format and time format
        self.formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(custom_module)s] %(message)s",
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
                print(f"Error rotating log file: {e}")
            
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
            print(f"Error cleaning up old logs: {e}")

    def emit(self, record):
        """Emit log record with structured data."""
        try:
            # Check if log rotation is needed
            self._rotate_logs_if_needed()
            
            # Set custom_module for consistent formatting
            if not hasattr(record, 'custom_module') or not getattr(record, 'custom_module', None):
                record.custom_module = getattr(record, 'module_name', getattr(record, 'mod_name', record.name))
            
            # Format base message using consistent formatter
            if self.formatter:
                base_msg = self.formatter.format(record)
            else:
                base_msg = record.getMessage()
            
            # Extract structured information for MESSAGE categories
            log_category = getattr(record, 'log_category', getattr(record, 'category', None))
            channel_name = getattr(record, 'channel_name', None)
            author_name = getattr(record, 'author_name', None)
            message_content = getattr(record, 'message_content', None)
            
            # Add structured context if available (for MESSAGE categories)
            msg = base_msg
            if log_category and 'MESSAGE' in log_category and any([channel_name, author_name, message_content]):
                context_parts = []
                if channel_name:
                    context_parts.append(f"CH:{channel_name}")
                if author_name:
                    context_parts.append(f"USER:{author_name}")
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
            print(f"Error saving guild config: {e}")
    
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


# Backward compatibility wrapper
def setup_logger(server_name: str, enable_colored_logs: bool = True) -> logging.Logger:
    """Legacy function wrapper for backward compatibility.
    
    Args:
        server_name: Server name for log setup
        enable_colored_logs: Enable colored console output
        
    Returns:
        Structured logger instance
    """
    # Treat server_name as guild_id for backward compatibility
    return setup_enhanced_logger(server_name, enable_colored_logs=enable_colored_logs)


# Legacy class name for backward compatibility
class StructuredRotatingFileHandler(GuildBasedRotatingFileHandler):
    """Legacy class name for backward compatibility."""
    pass


class TimedRotatingFileHandler(GuildBasedRotatingFileHandler):
    """Legacy class name for backward compatibility."""
    pass