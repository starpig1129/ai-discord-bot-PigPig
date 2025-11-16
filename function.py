import json
import os
import logging
import uuid
import traceback
import sys
import discord
from typing import Optional, Dict, Any, Union
from datetime import datetime, timezone
from utils.logger import LoggerMixin, log_error

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

class ErrorContext:
    """Structured error context for error reporting"""
    
    def __init__(self,
                 error: Exception,
                 details: Optional[str] = None,
                 guild_id: Optional[str] = None,
                 user_id: Optional[str] = None,
                 category: str = "SYSTEM",
                 correlation_id: Optional[str] = None):
        self.error = error
        self.details = details
        self.guild_id = guild_id
        self.user_id = user_id
        self.category = category
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self.timestamp = datetime.now(timezone.utc)
        self.error_type = type(error).__name__
        self.traceback = traceback.format_exception(type(self.error), self.error, self.error.__traceback__)
        
    def to_log_dict(self) -> Dict[str, Any]:
        """Convert context to structured logging dictionary"""
        return {
            "error_type": self.error_type,
            "error_message": str(self.error),
            "details": self.details,
            "guild_id": self.guild_id,
            "user_id": self.user_id,
            "category": self.category,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
            "traceback": self.traceback
        }

class Function(LoggerMixin):
    def __init__(self):
        LoggerMixin.__init__(self, "function")
        self.bot = None
        self.language_manager = None

    def set_bot(self, bot):
        self.bot = bot
        # Get language manager instance for localization
        if hasattr(bot, 'get_cog'):
            self.language_manager = bot.get_cog('LanguageManager')

    def _get_error_category(self, error: Exception, details: Optional[str] = None) -> str:
        """Determine error category based on error type and details"""
        error_type = type(error).__name__.lower()
        details_lower = (details or "").lower()
        
        if any(keyword in error_type for keyword in ['permission', 'unauthorized', 'forbidden']):
            return "PERMISSION"
        elif any(keyword in details_lower for keyword in ['database', 'sql', 'storage']):
            return "DATABASE"
        elif any(keyword in details_lower for keyword in ['network', 'http', 'connection', 'timeout']):
            return "EXTERNAL"
        elif any(keyword in details_lower for keyword in ['command', 'interaction', 'context']):
            return "USER_ACTION"
        elif any(keyword in details_lower for keyword in ['music', 'audio', 'player']):
            return "MULTIMEDIA"
        elif any(keyword in details_lower for keyword in ['translation', 'language', 'locale']):
            return "LOCALIZATION"
        elif any(keyword in error_type for keyword in ['key', 'attribute', 'index', 'value']):
            return "DATA"
        else:
            return "SYSTEM"

    def _localize_message(self, guild_id: str, key_path: str, fallback: Optional[str] = None, **kwargs) -> str:
        """Get localized message with fallback support"""
        if not self.language_manager:
            return fallback or key_path
        
        try:
            # Parse key path (e.g., "system.errors.unhandled")
            path_parts = key_path.split('.')
            if len(path_parts) >= 3 and path_parts[0] == "system":
                # System error messages are in system/errors.json
                if len(path_parts) == 3:
                    return self.language_manager.translate(guild_id, "system", "errors", path_parts[2], **kwargs)
                else:
                    return self.language_manager.translate(guild_id, "system", "errors", *path_parts[2:], **kwargs)
            else:
                return self.language_manager.translate(guild_id, *path_parts, **kwargs)
        except Exception:
            return fallback or key_path

    async def report_error(self, error: Exception, details: Optional[str] = None, guild_id: Optional[str] = None, user_id: Optional[str] = None):
        """Error reporting with structured logging and dual-language support
        
        Implements dual-language error handling:
        - English for system logs (technical details)
        - Localized for user-facing messages
        
        Args:
            error: The exception that occurred
            details: Additional context information
            guild_id: Discord guild/server ID for context and localization
            user_id: Discord user ID who triggered the error
        """
        if not self.bot:
            # Fallback to basic logging if bot not available
            logging.error(f"Error occurred before bot initialization: {error}", exc_info=error)
            return

        # Create structured error context
        category = self._get_error_category(error, details)
        error_context = ErrorContext(
            error=error,
            details=details,
            guild_id=guild_id,
            user_id=user_id,
            category=category
        )

        # Log error in English (system logs should be in English)
        self._log_structured_error(error_context)

        # Create user-facing embed with localization
        embed = await self._create_localized_error_embed(error_context)
        
        try:
            await self.bot.send_error_report(embed)
        except Exception as e:
            # Log failure to send error report but don't raise
            self.logger.error(f"Failed to send error report: {e}", exc_info=e)

    def _log_structured_error(self, context: ErrorContext):
        """Log error with structured format following technical specifications"""
        log_data = context.to_log_dict()
        
        # Use structured logging with context tracking
        self.error(
            f"Error in {context.category}: {context.error_type} - {context.error}",
            category=context.category,
            function_name="report_error",
            guild_id=context.guild_id,
            user_id=context.user_id,
            correlation_id=context.correlation_id,
            error_code=f"ERR_{context.category}_{context.error_type.upper()}",
            duration_ms=None,
            exc_info=context.error
        )

    async def _create_localized_error_embed(self, context: ErrorContext) -> discord.Embed:
        """Create localized error embed for user display"""
        import discord
        
        # Determine guild and user for localization
        guild_id = context.guild_id or "0"  # Default to global if no guild
        
        # Get localized strings
        title_key = f"system.errors.{context.category.lower()}_title"
        desc_key = f"system.errors.{context.category.lower()}_description"
        
        title = self._localize_message(guild_id, title_key, "Error Report")
        description = self._localize_message(
            guild_id, 
            desc_key, 
            context.details or "An unexpected error occurred"
        )

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.red()
        )

        # Add structured error information
        error_info = {
            "Error Type": context.error_type,
            "Timestamp": context.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC'),
            "Error Code": f"ERR_{context.category}_{context.error_type.upper()}",
            "Reference ID": context.correlation_id
        }

        if context.guild_id:
            error_info["Server ID"] = context.guild_id
        if context.user_id:
            error_info["User ID"] = context.user_id

        for field_name, field_value in error_info.items():
            embed.add_field(name=field_name, value=str(field_value), inline=True)

        # Add error message with proper truncation
        error_message = f"```{context.error_type}: {context.error}```"
        if len(error_message) > 1024:
            error_message = error_message[:1021] + "...```"
        embed.add_field(name="Error Details", value=error_message, inline=False)

        # Add truncated traceback for detailed debugging
        full_traceback = "".join(context.traceback)
        if len(full_traceback) > 1024:
            # Calculate proper truncation for traceback
            max_content_len = 1024 - len("```python\n\n```")
            truncated_traceback = full_traceback[:max_content_len - 3] + "..." if max_content_len > 3 else "..."
            traceback_value = f"```python\n{truncated_traceback}\n```"
        else:
            traceback_value = f"```python\n{full_traceback}\n```"
        
        embed.add_field(name="Debug Information", value=traceback_value, inline=False)
        
        # Add footer with timestamp and reference info
        embed.set_footer(
            text=f"Error ID: {context.correlation_id} | {context.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        
        return embed

    def open_json(self, path: str) -> dict:
        try:
            with open(os.path.join(ROOT_DIR, path), encoding="utf8") as json_file:
                return json.load(json_file)
        except:
            return {}

    def update_json(self, path: str, new_data: dict) -> None:
        data = self.open_json(path)
        if not data:
            return
        
        data.update(new_data)

        with open(os.path.join(ROOT_DIR, path), "w") as json_file:
            json.dump(data, json_file, indent=4)
func = Function()