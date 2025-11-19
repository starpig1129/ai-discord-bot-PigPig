from addons.logging import get_logger
from typing import Optional, Any, TYPE_CHECKING, List

import discord
from langchain_core.tools import tool

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

# Module-level logger
_logger = get_logger(server_id="Bot", source="llm.tools.emoji_tools")

class GuildEmojiTools:
    """Tools for accessing guild-specific emojis."""

    def __init__(self, runtime: "OrchestratorRequest"):
        self.runtime = runtime
        self.logger = getattr(self.runtime, "logger", _logger)

    def get_tools(self) -> list:
        runtime = self.runtime
        
        @tool
        def get_guild_emojis() -> str:
            """
            Retrieves a list of available custom emojis in the current server (guild).
            
            Use this tool when you want to see what custom emojis are available to use in your response.
            The output will be a formatted list of emojis that you can include in your message.
            """
            message = getattr(runtime, "message", None)
            if not message or not message.guild:
                return "No guild context available to fetch emojis."

            guild = message.guild
            if not hasattr(guild, "emojis"):
                return "No emojis found in this guild."
            
            emojis = guild.emojis
            if not emojis:
                return "This guild has no custom emojis."
                
            # Limit to avoid context overflow, though 50-100 is usually fine.
            # Sort by name for consistency
            sorted_emojis = sorted(emojis, key=lambda e: e.name)[:60]
            
            emoji_list = []
            for emoji in sorted_emojis:
                emoji_list.append(f"- {emoji.name}: {str(emoji)}")
                
            return "## Available Custom Emojis\nYou can use these emojis in your response:\n" + "\n".join(emoji_list)

        @tool
        async def add_reaction(emoji: str, message_id: Optional[str] = None) -> str:
            """
            Adds an emoji reaction to a specific message.
            
            Use this tool when you want to react to a user's message with an emoji (like a thumbs up, heart, or custom emoji).
            
            Args:
                emoji: The emoji to react with. Can be a unicode emoji (e.g., "👍") or a custom emoji name/ID.
                message_id: The ID of the message to react to. If not provided, reacts to the user's last message.
            """
            target_message = getattr(runtime, "message", None)
            
            # If message_id is provided, try to fetch that specific message
            if message_id:
                try:
                    # Try to find the message in the current channel
                    if target_message and target_message.channel:
                         try:
                            found_message = await target_message.channel.fetch_message(int(message_id))
                            if found_message:
                                target_message = found_message
                         except Exception:
                            pass # Fallback to original message if fetch fails
                except Exception:
                    pass

            if not target_message:
                return "Error: No message context available to react to."

            try:
                await target_message.add_reaction(emoji)
                return f"Successfully added reaction {emoji} to message."
            except discord.HTTPException as e:
                return f"Failed to add reaction: {str(e)}"
            except Exception as e:
                return f"Error adding reaction: {str(e)}"

        return [get_guild_emojis, add_reaction]
