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

"""User data management cog for Discord bot.

This module provides commands and utilities for managing personalized user data,
including preferences, display names, and interaction rules stored in a database.
"""

import json
from addons.logging import get_logger
import re
from typing import Any, Dict, List, Optional, Union, cast

# Module-level logger
log = get_logger(server_id="Bot", source=__name__)

import discord
from discord import app_commands
from discord.ext import commands
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from addons.settings import prompt_config
from cogs.memory.users.manager import SQLiteUserManager
from cogs.memory.users.models import UserInfo
from function import func
from llm.model_manager import ModelManager
from llm.utils.send_message import safe_edit_message

from .language_manager import LanguageManager

# Fallback translations for when LanguageManager is unavailable
FALLBACK_TRANSLATIONS = {
    "searching": "Searching your personal memory...",
    "updating": "Updating your personal memory...",
    "processing": "Processing...",
    "no_data_provided": "You didn't tell me what to remember.",
    "data_found": "I currently remember about you:\n{data}",
    "data_not_found": "I currently have no specific memory about you.",
    "data_updated": "Got it! I've remembered it!\nMy updated memory:\n{data}",
    "data_created": "Got it! I've remembered it!\nMy new memory:\n{data}",
    "sqlite_not_available": "Personal memory system not initialized",
    "invalid_action": "Invalid action. Please use 'save' or 'show'.",
    "database_error": "Database operation error: {error}",
    "ai_processing_failed": "AI processing error for your memory: {error}",
    "update_failed": "Failed to update your memory: {error}",
    "analysis_failed": "Data analysis failed: {error}",
    "invalid_user": "Invalid user ID",
    "invalid_response_format": "AI returned invalid response format"
}

# Default system prompt for user data agent
DEFAULT_SYSTEM_PROMPT = """You are a professional user data management assistant.
Intelligently merge existing user data with new data to return complete and accurate user information.
If the new data conflicts with the old data (e.g., a changed preference), the new data should take precedence and overwrite the conflicting part.
Maintain data integrity and consistency.
Always respond in Traditional Chinese."""


class UserDataResponse(BaseModel):
    """Structured response schema for user data agent.
    
    Attributes:
        procedural_memory: Free-form memory about user preferences and interactions.
        user_background: List of background information about the user.
        display_names: List of display names the user has used.
    """
    procedural_memory: Optional[str] = Field(
        default='',
        description="User's interaction preferences and conversation rules"
    )
    user_background: Optional[str] = Field(
        default='',
        description="User's interests, hobbies, and life background"
    )
    display_names: List[str] = Field(
        default_factory=list,
        description="Names the user wants to be called"
    )


class UserDataCog(commands.Cog):
    """Manages personalized user data for Discord bot interactions.
    
    Provides /memory command group allowing users to save or view bot's
    memory about them, such as preferences, nicknames, or interaction rules.
    
    Attributes:
        bot: The Discord bot instance.
        user_manager: Manager for user data persistence.
        lang_manager: Manager for multi-language support.
        logger: Logger instance for this cog.
    """

    memory_group = app_commands.Group(
        name="memory",
        description="Manage my personal memory and interaction preferences about you"
    )

    def __init__(
        self,
        bot: commands.Bot,
        user_manager: Optional[SQLiteUserManager] = None
    ) -> None:
        """Initializes the UserDataCog.
        
        Args:
            bot: The Discord bot instance.
            user_manager: Optional user manager instance. If None, will be
                injected during cog_load from bot.user_manager.
        """
        self.bot = bot
        self.user_manager = user_manager
        self.lang_manager: Optional[LanguageManager] = None
        self.logger = log

    async def cog_load(self) -> None:
        """Initializes language manager and user manager when cog loads."""
        self.lang_manager = LanguageManager.get_instance(self.bot)
        
        if not self.user_manager:
            self.user_manager = getattr(self.bot, 'user_manager', None)

    def _translate(
        self,
        guild_id: str,
        *path: str,
        fallback_key: str = '',
        **kwargs: Any
    ) -> str:
        """Unified translation method with fallback mechanism.
        
        Args:
            guild_id: Server ID for determining language.
            *path: Path in translation file.
            fallback_key: Fallback key in FALLBACK_TRANSLATIONS.
            **kwargs: Parameters for formatting translation string.
            
        Returns:
            Translated string, or fallback if translation fails.
        """
        if self.lang_manager:
            try:
                return self.lang_manager.translate(guild_id, *path, **kwargs)
            except Exception as e:
                self.logger.debug(f"Translation failed for path {path}: {e}")
        
        if fallback_key and fallback_key in FALLBACK_TRANSLATIONS:
            try:
                return FALLBACK_TRANSLATIONS[fallback_key].format(**kwargs)
            except (KeyError, ValueError) as e:
                self.logger.warning(f"Fallback formatting failed: {e}")
                return FALLBACK_TRANSLATIONS[fallback_key]
        
        return "Operation completed"

    def _get_guild_id_from_context(
        self,
        context: Union[discord.Interaction, discord.Message]
    ) -> str:
        """Extracts guild_id from various context types.
        
        Args:
            context: Discord interaction or message object.
            
        Returns:
            Guild ID string, or empty string if not found.
        """
        if isinstance(context, discord.Interaction):
            return str(context.guild_id) if context.guild_id else ''
        elif isinstance(context, discord.Message) and context.guild:
            return str(context.guild.id)
        return ''

    def _extract_json_from_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extracts and validates JSON from AI response text.
        
        Attempts multiple strategies to extract valid JSON:
        1. Direct JSON parsing
        2. Extracting from code fences (```json ... ```)
        3. Finding first {...} span
        
        Args:
            response_text: Raw text response from AI.
            
        Returns:
            Parsed JSON dictionary or None if extraction fails.
        """
        if not response_text or not isinstance(response_text, str):
            return None

        # Strategy 1: Direct parse
        try:
            parsed = json.loads(response_text.strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from code fences
        code_fence_pattern = r"```(?:json)?\s*(\{[\s\S]*?\})\s*```"
        match = re.search(code_fence_pattern, response_text, re.IGNORECASE)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find first {...} span
        start = response_text.find('{')
        end = response_text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(response_text[start:end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        return None

    def _validate_user_data_response(self, data: Dict[str, Any]) -> bool:
        """Validates that response contains expected user data fields.
        
        Args:
            data: Dictionary to validate.
            
        Returns:
            True if valid, False otherwise.
        """
        if not isinstance(data, dict):
            return False
        
        # Check for at least one expected field
        expected_fields = {"procedural_memory", "user_background", "display_names"}
        if not any(field in data for field in expected_fields):
            return False
        
        # Validate field types if present
        if "user_background" in data and not isinstance(data["user_background"], list):
            return False
        
        if "display_names" in data and not isinstance(data["display_names"], list):
            return False
        
        if "procedural_memory" in data and data["procedural_memory"] is not None:
            if not isinstance(data["procedural_memory"], str):
                return False
        
        return True

    def _extract_user_id_from_context(
        self,
        context: Union[discord.Interaction, discord.Message]
    ) -> Optional[str]:
        """Extracts user ID from context (interaction or message).
        
        Args:
            context: Discord interaction or message object.
            
        Returns:
            User ID string or None if not found.
        """
        if isinstance(context, discord.Interaction) and context.user:
            return str(context.user.id)
        elif isinstance(context, discord.Message) and context.author:
            return str(context.author.id)
        
        # Fallback: try to get author from generic context
        author = getattr(context, "author", None) or getattr(context, "user", None)
        if author and hasattr(author, "id"):
            return str(author.id)
        
        return None

    async def _read_user_data(
        self,
        user_id: str,
        context: Union[discord.Interaction, discord.Message]
    ) -> str:
        """Core logic for reading and formatting user's stored data.
        
        Args:
            user_id: Target user ID to read data for.
            context: Discord context for guild ID and fallback user.
            
        Returns:
            Formatted string with user data or error message.
        """
        guild_id = self._get_guild_id_from_context(context)
        
        try:
            if not self.user_manager:
                return self._translate(
                    guild_id,
                    "commands", "userdata", "errors", "sqlite_not_available",
                    fallback_key="sqlite_not_available"
                )

            user_info = await self.user_manager.get_user_info(user_id)

            # Fallback to message author if user not found
            if not user_info:
                author_id = self._extract_user_id_from_context(context)
                
                if author_id and author_id != user_id:
                    self.logger.info(
                        f"User {user_id} not found; falling back to author {author_id}"
                    )
                    try:
                        user_info = await self.user_manager.get_user_info(author_id)
                        if user_info:
                            user_id = author_id
                    except Exception as e:
                        self.logger.warning(
                            f"Fallback lookup for author {author_id} failed: {e}"
                        )

            if user_info:
                return f"""
                Preference: {user_info.procedural_memory}
                Background: {user_info.user_background}
                Display Names: {', '.join(user_info.display_names)}
                """

            return self._translate(
                guild_id,
                "commands", "userdata", "responses", "data_not_found",
                fallback_key="data_not_found",
                user_id=user_id
            )
            
        except Exception as e:
            self.logger.error(f"Failed to read user data for {user_id}: {e}")
            try:
                await func.report_error(
                    e,
                    f"Failed to read user data (user: {user_id})"
                )
            except Exception:
                pass
            
            return self._translate(
                guild_id,
                "commands", "userdata", "errors", "database_error",
                fallback_key="database_error",
                error=str(e)
            )

    async def _invoke_ai_merge_agent(
        self,
        existing_data: Optional[UserInfo],
        new_data: str,
        user_id: str
    ) -> UserDataResponse:
        """Invokes AI agent to merge existing and new user data."""
        system_prompt = (
            prompt_config.get_system_prompt('user_data_agent') or
            DEFAULT_SYSTEM_PROMPT
        )

        try:
            model, fallback = ModelManager().get_model("user_data_model")
        except Exception as e:
            await func.report_error(e, "Failed to get user_data_model")
            raise RuntimeError(f"Failed to get user_data_model: {e}") from e

        agent = create_agent(
            model=model,
            tools=[],
            system_prompt=system_prompt,
            response_format=UserDataResponse,
            middleware=cast(Any, [fallback,
                ModelCallLimitMiddleware(run_limit=1, exit_behavior="end"),
            ]),
        )

        existing_data_str = "No existing data"
        if existing_data:
            existing_dict = {
                "procedural_memory": existing_data.procedural_memory,
                "user_background": existing_data.user_background,
                "display_names": existing_data.display_names
            }
            existing_data_str = json.dumps(existing_dict, ensure_ascii=False, indent=2)

        user_prompt = (
            f"Existing user data:\n{existing_data_str}\n\n"
            f"New data to add:\n{new_data}\n\n"
            "Please merge these intelligently and return the complete merged result."
        )

        response = await agent.ainvoke({
            "messages": [HumanMessage(content=user_prompt)]
        })

        return response["structured_response"]

    async def _save_user_data(
        self,
        user_id: str,
        display_name: str,
        user_data: str,
        context: Union[discord.Interaction, discord.Message]
    ) -> str:
        """Core logic for saving user data with AI-assisted merge.
        
        Args:
            user_id: Target user ID.
            display_name: User's display name.
            user_data: New data to save.
            context: Discord context for guild ID.
            
        Returns:
            Success or error message string.
        """
        guild_id = self._get_guild_id_from_context(context)
        
        try:
            if not self.user_manager:
                return self._translate(
                    guild_id,
                    "commands", "userdata", "errors", "sqlite_not_available",
                    fallback_key="sqlite_not_available"
                )

            user_info = await self.user_manager.get_user_info(user_id)
 
            # Get existing procedural memory; if the user has no record, initialize one first.
            existing_data = user_info
            if not user_info:
                try:
                    # Create a minimal user record so downstream logic (and DB constraints) have a row to work with.
                    created = await self.user_manager.update_user_activity(user_id, display_name)
                    if created:
                        self.logger.info(f"Initialized user record for {user_id}")
                        # Attempt to fetch the freshly created record for the AI merge step.
                        try:
                            existing_data = await self.user_manager.get_user_info(user_id)
                        except Exception as e:
                            self.logger.warning(f"Re-fetch after init failed for {user_id}: {e}")
                    else:
                        self.logger.warning(f"Initialization of user record returned False for {user_id}")
                except Exception as e:
                    self.logger.error(f"Failed to initialize user record for {user_id}: {e}", exception=e)
                    try:
                        await func.report_error(e, f"Failed to initialize user record (user: {user_id})")
                    except Exception:
                        pass
 
            # Invoke AI agent to merge data
            try:
                merged_data = await self._invoke_ai_merge_agent(
                    existing_data,
                    user_data,
                    user_id
                )
            except Exception as e:
                self.logger.error(f"AI processing failed for user {user_id}: {e}")
                await func.report_error(
                    e,
                    f"AI processing user data failed (user: {user_id})"
                )
                
                return self._translate(
                    guild_id,
                    "commands", "userdata", "errors", "ai_processing_failed",
                    fallback_key="ai_processing_failed",
                    error=str(e)
                )

            # Persist to storage
            success = await self.user_manager.update_user_data(
                user_id,
                merged_data,
                display_name
            )
            
            if success:
                response_key = "data_updated" if existing_data else "data_created"
                
                # Format merged_data for display
                data_str = f"""
                Preference: {merged_data.procedural_memory}
                Background: {merged_data.user_background}
                Display Names: {','.join(merged_data.display_names)}
                """

                return self._translate(
                    guild_id,
                    "commands", "userdata", "responses", response_key,
                    fallback_key=response_key,
                    user_id=user_id,
                    data=data_str
                )
            else:
                self.logger.error(f"Database update failed for user {user_id}")
                await func.report_error(
                    Exception("Database update failed"),
                    f"Update user data failed (user: {user_id})"
                )
                
                return self._translate(
                    guild_id,
                    "commands", "userdata", "errors", "update_failed",
                    fallback_key="update_failed",
                    error="Database operation failed"
                )
                
        except Exception as e:
            self.logger.error(f"Failed to save user data for {user_id}: {e}")
            await func.report_error(
                e,
                f"Update user data failed (user: {user_id})"
            )
            
            return self._translate(
                guild_id,
                "commands", "userdata", "errors", "database_error",
                fallback_key="database_error",
                error=str(e)
            )

    @memory_group.command(
        name="save",
        description="Tell me something about you, and I'll remember it"
    )
    @app_commands.describe(
        preference="Information you want me to remember (e.g., 'My name is John')"
    )
    async def memory_save(
        self,
        interaction: discord.Interaction,
        preference: str
    ) -> None:
        """Handles /memory save command to store user preferences.
        
        Args:
            interaction: Discord interaction object.
            preference: String data user wants to be remembered.
        """
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        await interaction.response.defer(thinking=True, ephemeral=True)
        
        result = await self.manage_user_data(
            context=interaction,
            user=interaction.user,
            user_data=preference,
            action='save'
        )
        
        await interaction.followup.send(result, ephemeral=True)

    @memory_group.command(
        name="show",
        description="View everything I currently remember about you"
    )
    async def memory_show(self, interaction: discord.Interaction) -> None:
        """Handles /memory show command to display stored user preferences.
        
        Args:
            interaction: Discord interaction object.
        """
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)

        await interaction.response.defer(thinking=True, ephemeral=True)
        
        result = await self.manage_user_data(
            context=interaction,
            user=interaction.user,
            user_data='',
            action='read'
        )
        
        await interaction.followup.send(result, ephemeral=True)

    async def manage_user_data(
        self,
        context: Union[discord.Interaction, discord.Message],
        user: Union[discord.User, discord.Member],
        user_data: str = '',
        action: str = 'read',
        message_to_edit: Optional[discord.Message] = None
    ) -> str:
        """Dispatcher for managing user data operations.
        
        Args:
            context: Interaction or message context.
            user: Target user object.
            user_data: Optional data to save (only used for 'save' action).
            action: Either 'read' or 'save'.
            message_to_edit: Optional message object to edit during processing.
            
        Returns:
            Operation result string.
        """
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)
        
        guild_id = self._get_guild_id_from_context(context)
        
        if not self.user_manager:
            return self._translate(
                guild_id,
                "commands", "userdata", "errors", "sqlite_not_available",
                fallback_key="sqlite_not_available"
            )
        
        user_id = str(user.id)
        
        # Update status message if provided
        if message_to_edit:
            status_key_map = {
                'read': 'searching',
                'save': 'updating'
            }
            message_key = status_key_map.get(action, 'processing')
            
            status_message = self._translate(
                guild_id,
                "commands", "userdata", "responses", message_key,
                fallback_key=message_key
            )
            await safe_edit_message(message_to_edit, status_message)

        # Route to appropriate handler
        if action == 'read':
            return await self._read_user_data(user_id, context)
        elif action == 'save':
            if not user_data or not user_data.strip():
                return self._translate(
                    guild_id,
                    "commands", "userdata", "responses", "no_data_provided",
                    fallback_key="no_data_provided"
                )
            return await self._save_user_data(
                user_id,
                user.display_name,
                user_data,
                context
            )
        else:
            return self._translate(
                guild_id,
                "commands", "userdata", "responses", "invalid_action",
                fallback_key="invalid_action"
            )

    async def manage_user_data_message(
        self,
        message: Union[discord.Interaction, discord.Message],
        user_id: Optional[str] = None,
        user_data: str = '',
        action: str = 'read',
        message_to_edit: Optional[discord.Message] = None
    ) -> str:
        """Manages user data triggered from message (for internal tool use).
        
        Args:
            message: Triggering Discord message object.
            user_id: Optional target user ID.
            user_data: Optional data to save.
            action: Either 'read' or 'save'.
            message_to_edit: Optional message to edit.
            
        Returns:
            Operation result string.
        """
        guild_id = self._get_guild_id_from_context(message)
        
        try:
            # Resolve user_id
            if user_id == "<@user_id>" or user_id is None:
                user_id = self._extract_user_id_from_context(message)
            else:
                match = re.search(r'\d+', str(user_id))
                user_id = match.group() if match else None

            if not user_id:
                return self._translate(
                    guild_id,
                    "commands", "userdata", "errors", "invalid_user",
                    fallback_key="invalid_user"
                )

            # Fetch user object
            user = await self.bot.fetch_user(int(user_id))

            # Execute operation
            result = await self.manage_user_data(
                message,
                user,
                user_data,
                action,
                message_to_edit
            )
            return result

        except (ValueError, discord.NotFound) as e:
            self.logger.warning(f"Invalid or not found user_id {user_id}: {e}")
            return self._translate(
                guild_id,
                "commands", "userdata", "errors", "invalid_user",
                fallback_key="invalid_user"
            )
        except Exception as e:
            self.logger.error(
                f"manage_user_data_message error for user_id={user_id}: {e}"
            )
            await func.report_error(
                e,
                f"manage_user_data_message error for user_id={user_id}"
            )
            
            return self._translate(
                guild_id,
                "commands", "userdata", "errors", "analysis_failed",
                fallback_key="analysis_failed",
                error=str(e)
            )

    async def get_user_statistics(self) -> Dict[str, Any]:
        """Retrieves user statistics from user manager.
        
        Returns:
            Dictionary containing statistics, or error message.
        """
        if not self.user_manager:
            return {"error": "User manager not initialized"}
        
        try:
            return await self.user_manager.get_user_statistics()
        except Exception as e:
            self.logger.error(f"Failed to get user statistics: {e}")
            return {"error": str(e)}

    async def update_user_activity(
        self,
        user_id: str,
        display_name: str = ''
    ) -> bool:
        """Updates user activity status.
        
        Args:
            user_id: User ID string.
            display_name: Optional user display name.
            
        Returns:
            True if successful, False otherwise.
        """
        if not self.user_manager:
            return False
        
        try:
            return await self.user_manager.update_user_activity(
                user_id,
                display_name
            )
        except Exception as e:
            self.logger.error(f"Failed to update user activity: {e}")
            return False


async def setup(bot: commands.Bot) -> None:
    """Sets up the UserDataCog.
    
    Args:
        bot: The Discord bot instance.
    """
    # Check if memory system is enabled before loading
    from addons.settings import memory_config
    
    if not getattr(memory_config, "enabled", True):
        log.info("Memory system is disabled in memory.yaml, skipping UserDataCog.")
        return
    
    user_manager = getattr(bot, 'user_manager', None)
    cog = UserDataCog(bot, user_manager=user_manager)
    await bot.add_cog(cog)

