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
            Retrieves all custom emojis available in the current server.

            Call this tool when:
            - The user asks to use or see custom emojis.
            - You want to react to a message with a custom guild emoji (call this first to find the emoji name).
            - The response agent will need custom emoji strings (e.g. `<:pig_smile:123456>`) in its reply.
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
            React to a message with an emoji — a supplementary action alongside your text response.

            Use on most messages. Pick the emoji that fits the specific tone and content naturally.
            Any unicode emoji works without prior lookup.

            Only call `get_guild_emojis` first if you want a server custom emoji by name.

            Args:
                emoji: Unicode emoji (e.g. "👍") or custom guild emoji name (e.g. "pig_smile").
                message_id: Target message ID from context (`[... | MessageID:12345]`). Defaults to triggering message.
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
        async def get_guild_stickers() -> str:
            """
            Retrieves stickers available to send. Always call this before `send_sticker`.

            Returns guild-specific stickers first. If the guild has none, returns stickers
            from Discord's standard sticker packs (free, always usable).

            Call this tool when:
            - The user asks to use or see stickers.
            - You intend to call `send_sticker` — the sticker ID returned here is required.
            """
            message = getattr(runtime, "message", None)
            if not message or not message.guild:
                return "No guild context available to fetch stickers."

            guild = message.guild
            guild_stickers = getattr(guild, "stickers", [])

            if guild_stickers:
                sorted_stickers = sorted(guild_stickers, key=lambda s: s.name)[:30]
                sticker_list = [f"- {s.name} (ID: {s.id})" for s in sorted_stickers]
                return "## Guild Stickers\n" + "\n".join(sticker_list)

            # Fallback: Discord premium/standard sticker packs
            try:
                client = message._state._get_client()
                packs = await client.fetch_premium_sticker_packs()
                sticker_list = []
                for pack in packs:
                    for sticker in list(pack.stickers)[:5]:
                        sticker_list.append(f"- {sticker.name} (ID: {sticker.id}) [pack: {pack.name}]")
                    if len(sticker_list) >= 30:
                        break
                if sticker_list:
                    return "## Standard Discord Stickers (guild has no custom stickers)\n" + "\n".join(sticker_list)
            except Exception as e:
                return f"No stickers available (guild has none; standard pack fetch failed: {type(e).__name__}: {e})"

            return "No stickers available."

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
            if not message or not message.channel:
                return "No channel context available."

            sticker = None
            sid = int(sticker_id)

            # Try guild sticker first, then fall back to standard sticker
            if message.guild:
                try:
                    sticker = await message.guild.fetch_sticker(sid)
                except Exception:
                    pass

            if sticker is None:
                try:
                    client = message._state._get_client()
                    sticker = await client.fetch_sticker(sid)
                except Exception:
                    pass

            if sticker is None:
                return f"Error: Sticker {sticker_id} not found in guild or standard packs."

            try:
                await message.channel.send(stickers=[sticker], reference=message)
                return f"Successfully sent sticker: {sticker.name}"
            except discord.Forbidden:
                return "Error: I don't have permission to send stickers."
            except Exception as e:
                return f"Error sending sticker: {str(e)}"

        @tool
        async def change_own_nickname(new_nickname: str) -> str:
            """
            Changes your own nickname in the current server.

            You are encouraged to call this proactively when the mood, roleplay, or
            conversation topic calls for a different persona (e.g. "Angry PigPig",
            "Detective Pig", "Chef Pig"). The nickname change takes effect immediately
            and will be visible to everyone in the server.

            Args:
                new_nickname: The new nickname to adopt. Max 32 characters.
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
            Pauses for a specified number of seconds BEFORE the text response appears,
            while keeping the 'typing...' indicator active in Discord.

            Use this to create comedic timing or suspense — the bot will appear to be
            thinking, then the response will arrive after the pause.

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

        # Mark action tools for the message agent.
        # Primary: set directly on the tool's __dict__ (readable via hasattr/getattr on Pydantic model).
        # Fallback: set on .coroutine or .func for older LangChain versions.
        for _t in (add_reaction, send_sticker, change_own_nickname, delete_own_last_message, dramatic_pause):
            try:
                _t.__dict__["target_agent_mode"] = "message"
            except Exception:
                fn = getattr(_t, "coroutine", None) or getattr(_t, "func", None)
                if fn is not None:
                    fn.target_agent_mode = "message"

        return [get_guild_emojis, add_reaction, get_guild_stickers, send_sticker, change_own_nickname, delete_own_last_message, dramatic_pause]