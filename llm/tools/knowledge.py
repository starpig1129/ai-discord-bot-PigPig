"""Knowledge tools for managing guild and channel level memories.

This module provides tools for the LLM to store and update shared information
like inside jokes, relationships, aliases, and special events.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

import discord
from function import func
from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="llm.tools.knowledge")

class UpdateKnowledgeInput(BaseModel):
    """Input for updating knowledge."""
    new_information: str = Field(description="The new cultural fact or information to add/update.")
    category: str = Field(
        default="general", 
        description="Category of information: 'inside_joke', 'relationship', 'alias', 'special_event', or 'general'."
    )

class UpdateGuildKnowledgeTool(BaseTool):
    """Tool to update knowledge shared across the entire server."""
    name: str = "update_guild_knowledge"
    description: str = "Record or update facts, memes, or culture for the ENTIRE SERVER. Use when information affects everyone in the guild."
    args_schema: Type[BaseModel] = UpdateKnowledgeInput
    runtime: Optional[Any] = None

    def _run(self, new_information: str, category: str = "general") -> str:
        """Synchronous run (not used)."""
        raise NotImplementedError("Use _arun")

    async def _arun(self, new_information: str, category: str = "general") -> str:
        """Update guild-level knowledge."""
        if not self.runtime or not self.runtime.message:
            return "Error: Runtime context missing."

        guild = self.runtime.message.guild
        if not guild:
            return "Error: This tool can only be used within a Discord Server (Guild)."

        bot = self.runtime.bot
        cog = bot.get_cog("UserDataCog")
        if not cog:
            return "Error: UserDataCog not loaded."

        try:
            result = await cog._save_knowledge_data(
                target_type="guild",
                target_id=str(guild.id),
                content=new_information,
                category=category,
                context=self.runtime.message
            )
            return result
        except Exception as e:
            logger.error(f"update_guild_knowledge tool failed: {e}")
            return f"Error updating guild knowledge: {str(e)}"

class UpdateChannelKnowledgeTool(BaseTool):
    """Tool to update knowledge specific to the current channel."""
    name: str = "update_channel_knowledge"
    description: str = "Record or update facts, rules, or culture for the CURRENT CHANNEL only. Use for channel-specific nicknames or local context."
    args_schema: Type[BaseModel] = UpdateKnowledgeInput
    runtime: Optional[Any] = None

    def _run(self, new_information: str, category: str = "general") -> str:
        """Synchronous run (not used)."""
        raise NotImplementedError("Use _arun")

    async def _arun(self, new_information: str, category: str = "general") -> str:
        """Update channel-level knowledge."""
        if not self.runtime or not self.runtime.message:
            return "Error: Runtime context missing."

        channel = self.runtime.message.channel
        bot = self.runtime.bot
        cog = bot.get_cog("UserDataCog")
        if not cog:
            return "Error: UserDataCog not loaded."

        try:
            result = await cog._save_knowledge_data(
                target_type="channel",
                target_id=str(channel.id),
                content=new_information,
                category=category,
                context=self.runtime.message
            )
            return result
        except Exception as e:
            logger.error(f"update_channel_knowledge tool failed: {e}")
            return f"Error updating channel knowledge: {str(e)}"

def get_tools(runtime: Any) -> list:
    """Discovery function for the tools factory."""
    return [
        UpdateGuildKnowledgeTool(runtime=runtime),
        UpdateChannelKnowledgeTool(runtime=runtime),
    ]

class KnowledgeTools:
    """Wrapper class for discovering knowledge management tools.
    Supported by the factory but get_tools() is preferred.
    """
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def get_tools(self) -> list:
        """Return list of knowledge tools with shared runtime."""
        return get_tools(self.runtime)
