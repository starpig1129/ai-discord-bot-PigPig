import asyncio

from typing import List, Optional

import discord

from llm.prompting.manager import get_prompt_manager
from function import func

# Logger
_logger = logging.getLogger(__name__)

def get_channel_system_prompt(
  channel_id: str,
  guild_id: str,
  bot_id: str,
  message: Optional[discord.Message] = None,
) -> str:
  """Gets channel-specific system prompt with three-tier inheritance.
  
  Integrates three-tier inheritance: YAML base + server level + channel level.
  
  Args:
      channel_id: Channel ID.
      guild_id: Server/guild ID.
      bot_id: Discord bot ID.
      message: Discord message object (for language detection).
  
  Returns:
      Complete system prompt string with three-tier inheritance.
  """
  try:
      _logger.debug(
          "Getting channel system prompt - channel: %s, guild: %s",
          channel_id,
          guild_id,
      )
      
      # Get bot instance
      bot = None
      if message and hasattr(message, "guild") and message.guild:
          bot = message.guild.me._state._get_client()
      
      # Try to get SystemPromptManagerCog
      system_prompt_cog = None
      if bot and hasattr(bot, "get_cog"):
          system_prompt_cog = bot.get_cog("SystemPromptManagerCog")
      
      if not system_prompt_cog:
          _logger.warning(
              "SystemPromptManagerCog unavailable, cannot get channel %s prompt",
              channel_id,
          )
          return ""
      
      manager = system_prompt_cog.get_system_prompt_manager()
      
      # Clear cache to ensure latest data
      try:
          manager.cache.invalidate(guild_id, channel_id)
          _logger.debug("Cleared channel cache: %s:%s", guild_id, channel_id)
      except Exception as cache_error:
          _logger.warning("Failed to clear channel cache: %s", cache_error)
      
      # Get effective prompt with three-tier inheritance
      effective_prompt = manager.get_effective_prompt(
          channel_id, guild_id, message
      )
      
      if not effective_prompt or "prompt" not in effective_prompt:
          return ""
      
      prompt = effective_prompt["prompt"]
      source = effective_prompt.get("source", "unknown")
      
      _logger.info(
          "Channel system prompt - source: %s, channel: %s",
          source,
          channel_id,
      )
      
      # Handle different sources
      if source in ["channel", "server"]:
          _logger.info("Using %s level custom prompt", source)
          return prompt
      
      if source == "yaml":
          _logger.debug("Only YAML base prompt, returning empty string")
          return ""
      
      return prompt
  
  except Exception as exc:
      asyncio.create_task(
          func.report_error(
              exc, f"Channel system prompt retrieval for channel {channel_id} failed"
          )
      )
      return ""


def get_system_prompt(bot_id: str, message: Optional[discord.Message] = None) -> str:
  """Gets system prompt with fallback hierarchy.
  
  Priority order:
  1. Channel-specific system prompt (if exists and valid)
  2. Server-level system prompt (if exists and valid)
  3. YAML global default prompt
  4. Hardcoded fallback prompt
  
  Args:
      bot_id: Discord bot ID.
      message: Discord message object (for language detection and channel info).
  
  Returns:
      Complete system prompt string.
  """
  # Try channel-specific prompt first
  if message and hasattr(message, "channel") and hasattr(message, "guild"):
      try:
          channel_prompt = get_channel_system_prompt(
              str(message.channel.id), str(message.guild.id), bot_id, message
          )
          if channel_prompt and channel_prompt.strip():
              return channel_prompt
      except Exception as exc:
          asyncio.create_task(
              func.report_error(exc, "Channel system prompt retrieval failed")
          )
  
  # Fallback to YAML prompt management system
  try:
      prompt_manager = get_prompt_manager()
      if prompt_manager:
          return prompt_manager.get_system_prompt(bot_id, message)
  except Exception as exc:
      asyncio.create_task(
          func.report_error(exc, "YAML prompt manager system failed")
      )
  
  # Final fallback: hardcoded basic prompt
  _logger.warning("Using fallback hardcoded system prompt")
  return """You are a helpful AI assistant. Please:
1. Be concise and clear in your responses
2. Answer in the same language as the user
3. Be respectful and professional"""
