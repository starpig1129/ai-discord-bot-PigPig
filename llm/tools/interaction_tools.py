from addons.logging import get_logger
from typing import Optional, Any, TYPE_CHECKING, List

import discord
import asyncio
from langchain_core.tools import tool

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

# Module-level logger
_logger = get_logger(server_id="Bot", source="llm.tools.interaction_tools")

class DiscordInteractionTools:
    """Tools for advanced Discord interactions (Emojis, Polls, Stickers)."""

    def __init__(self, runtime: "OrchestratorRequest"):
        self.runtime = runtime
        self.logger = getattr(self.runtime, "logger", _logger)

    def get_tools(self) -> list:
        runtime = self.runtime
        
        # Helper to get target message
        async def _get_target_message(message_id: Optional[str]) -> Optional[discord.Message]:
            target_message = getattr(runtime, "message", None)
            if message_id:
                try:
                    if target_message and target_message.channel:
                         try:
                            found_message = await target_message.channel.fetch_message(int(message_id))
                            if found_message:
                                return found_message
                         except Exception:
                            pass
                except Exception:
                    pass
            return target_message

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
                
            # Limit to avoid context overflow
            sorted_emojis = sorted(emojis, key=lambda e: e.name)[:60]
            
            emoji_list = []
            for emoji in sorted_emojis:
                emoji_list.append(f"- {emoji.name}: {str(emoji)}")
                
            return "## Available Custom Emojis\nYou can use these emojis in your response:\n" + "\n".join(emoji_list)

        @tool
        async def add_reaction(emoji: str, message_id: Optional[str] = None) -> str:
            """
            Adds an emoji reaction to a specific message.
            
            Use this tool to react to a message (e.g., thumbs up, or custom emoji).
            IMPORTANT: To target a specific past message, find its ID in the memory 
            context formatted as `[... | MessageID:12345]` and pass '12345' as message_id.
            If not provided, reacts to the triggering message.
            
            Args:
                emoji: The emoji to react with. Can be unicode (e.g. "👍") or a custom emoji name (e.g. "pig_smile").
                message_id: The ID of the message to react to. Must be extracted from memory.
            """
            target_message = await _get_target_message(message_id)
            if not target_message:
                return "Error: No message context available to react to."

            # Smart Emoji Resolution
            actual_emoji = emoji
            message = getattr(runtime, "message", None)
            # Check if it's likely a custom emoji name (not unicode, not already formatted `<:name:id>`)
            if message and getattr(message, "guild", None) and not emoji.startswith("<") and len(emoji) > 1:
                # Try to find matching guild emoji by name
                for e in getattr(message.guild, "emojis", []):
                    if e.name.lower() == emoji.lower() or emoji.lower() in e.name.lower():
                        actual_emoji = e
                        break

            try:
                await target_message.add_reaction(actual_emoji)
                return f"Successfully added reaction {emoji} to message."
            except discord.HTTPException as e:
                return f"Failed to add reaction: {str(e)}"
            except Exception as e:
                return f"Error adding reaction: {str(e)}"
        
        @tool
        def get_guild_stickers() -> str:
            """
            Retrieves a list of available stickers in the current server (guild).
            """
            message = getattr(runtime, "message", None)
            if not message or not message.guild:
                return "No guild context available to fetch stickers."

            guild = message.guild
            if not hasattr(guild, "stickers"):
                return "No stickers found in this guild."
            
            stickers = guild.stickers
            if not stickers:
                return "This guild has no stickers."
                
            sorted_stickers = sorted(stickers, key=lambda s: s.name)[:30]
            
            sticker_list = []
            for sticker in sorted_stickers:
                sticker_list.append(f"- {sticker.name} (ID: {sticker.id})")
                
            return "## Available Stickers\n" + "\n".join(sticker_list)

        @tool
        async def send_sticker(sticker_id: str) -> str:
            """
            Sends a sticker to the channel.
            
            NOTE: Stickers are sent as an immediate, standalone message separate from your 
            main text response stream. Please coordinate your conversational flow accordingly.
            
            Args:
                sticker_id: The ID of the sticker to send. You must get this ID from `get_guild_stickers` first.
            """
            message = getattr(runtime, "message", None)
            if not message or not message.guild:
                return "No guild context available."
            
            try:
                sticker = await message.guild.fetch_sticker(int(sticker_id))
                await message.channel.send(stickers=[sticker])
                return f"Successfully sent sticker: {sticker.name}"
            except discord.NotFound:
                return "Error: Sticker not found."
            except discord.Forbidden:
                return "Error: I don't have permission to send stickers."
            except Exception as e:
                return f"Error sending sticker: {str(e)}"

        @tool
        async def change_own_nickname(new_nickname: str) -> str:
            """
            Changes your own nickname in the current server to fit the roleplay or atmosphere.
            
            Args:
                new_nickname: The new name you want to adopt (e.g. "Angry PigPig", "Detective Pig"). Max 32 characters.
            """
            message = getattr(runtime, "message", None)
            if not message or not message.guild or not message.guild.me:
                return "Error: Guild context unavailable."
            
            try:
                await message.guild.me.edit(nick=new_nickname[:32])
                return f"Successfully changed my local nickname to {new_nickname}"
            except discord.Forbidden:
                return "Error: I lack the 'Change Nickname' permission in this server."
            except Exception as e:
                return f"Error changing nickname: {str(e)}"

        @tool
        async def delete_own_last_message() -> str:
            """
            Deletes the last message YOU (the bot) sent in this channel.
            
            Use this for dramatic effect, self-correction, or if you change your mind about what you just said.
            """
            message = getattr(runtime, "message", None)
            if not message or not message.channel:
                return "Error: Channel context unavailable."
            
            try:
                # Find the most recent message by the bot
                async for msg in message.channel.history(limit=20):
                    if msg.author.id == message.guild.me.id:
                        await msg.delete()
                        return "Successfully retracted/deleted my previous message."
                return "No visible recent messages from me to delete."
            except Exception as e:
                return f"Error retracting message: {str(e)}"

        @tool
        async def dramatic_pause(seconds: int) -> str:
            """
            Pauses for a specified number of seconds before continuing your response, 
            while keeping the 'typing...' indicator active.
            
            Use this to create comedic timing, suspense, or a thoughtful pause in your conversation.
            
            Args:
                seconds: Number of seconds to pause (maximum 10).
            """
            pause_time = min(max(1, seconds), 10)
            message = getattr(runtime, "message", None)
            
            try:
                if message and message.channel:
                    async with message.channel.typing():
                        await asyncio.sleep(pause_time)
                else:
                    await asyncio.sleep(pause_time)
                return f"Paused dramatically for {pause_time} seconds."
            except Exception as e:
                return f"Pause failed: {str(e)}"

        return [get_guild_emojis, add_reaction, get_guild_stickers, send_sticker, change_own_nickname, delete_own_last_message, dramatic_pause]