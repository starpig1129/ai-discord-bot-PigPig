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
Logging system implementation following technical specifications.

This module provides structured logging capabilities with:
- Log format with context information
- Server isolation architecture
- Correlation ID tracking
- Performance monitoring integration
"""

import logging
import os
import uuid
import sys
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Standard log format template as per specifications
LOG_FORMAT = (
    "[%(asctime)s] [%(levelname)s] [%(log_category)s] [%(custom_module)s] [%(function_name)s] "
    "[GUILD:%(guild_id)s] [USER:%(user_id)s] %(message)s"
)

#  Format with additional context fields
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
            if self.simple_format:
                # Simple format: just use the base formatter directly
                msg = self.base_formatter.format(record)
            else:
                # Enhanced format: add extra context
                # Initialize extra context dictionary
                extra_context = {}
                
                # Extract or set defaults for structured logging
                extra_context['log_category'] = getattr(record, 'category', 'SYSTEM')
                extra_context['custom_module'] = getattr(record, 'mod_name',
                                                        getattr(record, 'module_name', record.name))
                
                # Extract function name with better fallback logic
                function_name = 'unknown'
                if getattr(record, 'function_name', None):
                    function_name = getattr(record, 'function_name')
                elif getattr(record, 'function', None):
                    function_name = getattr(record, 'function')
                elif getattr(record, 'funcName', None):
                    function_name = getattr(record, 'funcName')
                elif hasattr(record, 'name') and '.' in record.name:
                    function_name = record.name.split('.')[-1]
                
                extra_context['function_name'] = function_name
                extra_context['guild_id'] = getattr(record, 'guild_id', 'N/A')
                extra_context['user_id'] = getattr(record, 'user_id', 'N/A')
                extra_context['correlation_id'] = getattr(record, 'correlation_id', str(uuid.uuid4())[:8])
                extra_context['duration_ms'] = getattr(record, 'duration_ms', None)
                extra_context['error_code'] = getattr(record, 'error_code', None)
                
                # Format extra context for display
                extra_context_parts = []
                if extra_context.get('duration_ms'):
                    extra_context_parts.append(f"[DUR:{extra_context['duration_ms']:.1f}ms]")
                if extra_context.get('error_code'):
                    extra_context_parts.append(f"[ERR:{extra_context['error_code']}]")
                
                extra_context['extra_context'] = ' '.join(extra_context_parts)
                
                # Add extra context to record for formatter access
                record.__dict__.update(extra_context)
                
                # Format message
                msg = self.base_formatter.format(record)
            
            # Apply colors if enabled
            colored_msg = apply_colors(msg, self.enable_colored_logs)
            
            # Print message
            print(colored_msg)
            
        except Exception:
            self.handleError(record)


class StructuredRotatingFileHandler(logging.Handler):
    """Structured rotating file handler with structured logging support.
    
    Implements the new log format with contextual information including:
    - Correlation ID for request tracing
    - Performance monitoring (duration_ms)
    - Error categorization (error_code)
    - Guild/user context tracking
    """
    
    def __init__(self, server_name: str):
        super().__init__()
        self.server_name = server_name
        self.current_date = datetime.now().strftime('%Y%m%d')
        self.current_hour = datetime.now().strftime('%H')
        self._create_new_folder()
        self._open_new_file()
        
        # Structured formatter with structured data support
        self.formatter = logging.Formatter(
            ENHANCED_FORMAT,
            datefmt='%Y-%m-%dT%H:%M:%S'
        )

    def _create_new_folder(self):
        """Create server-specific log directory structure."""
        log_directory = f'logs/{self.server_name}/{self.current_date}'
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)
        self.log_directory = log_directory

    def _open_new_file(self):
        """Open hourly log file for current server."""
        log_filename = os.path.join(
            self.log_directory, 
            f'bot_log_{self.current_hour}.log'
        )
        self.stream = open(log_filename, 'a', encoding='utf-8')

    def emit(self, record):
        """Emit log record with structured data."""
        try:
            current_date = datetime.now().strftime('%Y%m%d')
            current_hour = datetime.now().strftime('%H')
            
            # Handle hourly rotation
            if current_date != self.current_date or current_hour != self.current_hour:
                self.stream.close()
                self.current_date = current_date
                self.current_hour = current_hour
                self._create_new_folder()
                self._open_new_file()
            
            # Initialize extra context dictionary
            extra_context = {}
            
            # Extract or set defaults for structured logging
            # Use custom attribute names to avoid conflicts with LogRecord built-ins
            extra_context['log_category'] = getattr(record, 'category', 'SYSTEM')
            extra_context['custom_module'] = getattr(record, 'mod_name',
                                                    getattr(record, 'module_name', record.name))
            # Extract function name with better fallback logic
            function_name = 'unknown'
            if getattr(record, 'function_name', None):
                function_name = getattr(record, 'function_name')
            elif getattr(record, 'function', None):
                function_name = getattr(record, 'function')
            elif getattr(record, 'funcName', None):
                function_name = getattr(record, 'funcName')
            elif hasattr(record, 'name') and '.' in record.name:
                # Fallback to last part of module name
                function_name = record.name.split('.')[-1]
            
            extra_context['function_name'] = function_name
            extra_context['guild_id'] = getattr(record, 'guild_id', 'N/A')
            extra_context['user_id'] = getattr(record, 'user_id', 'N/A')
            extra_context['correlation_id'] = getattr(record, 'correlation_id', str(uuid.uuid4())[:8])
            extra_context['duration_ms'] = getattr(record, 'duration_ms', None)
            extra_context['error_code'] = getattr(record, 'error_code', None)
            
            # Format extra context for display
            extra_context_parts = []
            if extra_context.get('duration_ms'):
                extra_context_parts.append(f"[DUR:{extra_context['duration_ms']:.1f}ms]")
            if extra_context.get('error_code'):
                extra_context_parts.append(f"[ERR:{extra_context['error_code']}]")
            
            extra_context['extra_context'] = ' '.join(extra_context_parts)
            
            # Add extra context to record for formatter access
            record.__dict__.update(extra_context)
            
            # Format message with template
            if hasattr(self, 'formatter') and self.formatter is not None:
                msg = self.formatter.format(record)
            else:
                msg = record.getMessage()
            self.stream.write(msg + '\n')
            self.stream.flush()
            
        except Exception:
            self.handleError(record)

    def close(self):
        """Clean up server-specific resources."""
        if hasattr(self, 'stream'):
            self.stream.close()
        super().close()


def setup_enhanced_logger(server_name: str, 
                         level: str = "INFO",
                         enable_colored_logs: bool = True) -> logging.Logger:
    """Setup logging system with category separation and color support.
    
    Args:
        server_name: Discord guild name for log separation
        level: Minimum log level
        enable_colored_logs: Enable colored console output
        
    Returns:
        Logger instance with structured logging
    """
    
    # Use server name as logger name for isolation
    logger = logging.getLogger(server_name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers to prevent duplication
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Create structured file handler
    handler = StructuredRotatingFileHandler(server_name)
    logger.addHandler(handler)
    
    # Add console handler for development (only if environment variable set)
    if os.getenv('ENABLE_CONSOLE_LOGGING', 'false').lower() == 'true':
        console_handler = ColoredConsoleHandler(enable_colored_logs, simple_format=True)
        logger.addHandler(console_handler)
    
    return logger


# Backward compatibility wrapper
def setup_logger(server_name: str, enable_colored_logs: bool = True) -> logging.Logger:
    """Legacy function wrapper for backward compatibility.
    
    Args:
        server_name: Server name for log setup
        enable_colored_logs: Enable colored console output
        
    Returns:
        Structured logger instance
    """
    return setup_enhanced_logger(server_name, enable_colored_logs=enable_colored_logs)


# Legacy class name for backward compatibility
class TimedRotatingFileHandler(StructuredRotatingFileHandler):
    """Legacy class name for backward compatibility."""
    pass