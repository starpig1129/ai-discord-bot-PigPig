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
            msg = self.format(record)
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
                         level: str = "INFO") -> logging.Logger:
    """Setup logging system with category separation.
    
    Args:
        server_name: Discord guild name for log separation
        level: Minimum log level
        
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
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(console_handler)
    
    return logger


# Backward compatibility wrapper
def setup_logger(server_name: str) -> logging.Logger:
    """Legacy function wrapper for backward compatibility.
    
    Args:
        server_name: Server name for log setup
        
    Returns:
        Structured logger instance
    """
    return setup_enhanced_logger(server_name)


# Legacy class name for backward compatibility
class TimedRotatingFileHandler(StructuredRotatingFileHandler):
    """Legacy class name for backward compatibility."""
    pass
