# MIT License
# Music playback tools for LLM integration.

from typing import Optional, Any, TYPE_CHECKING
from langchain_core.tools import tool
from addons.logging import get_logger
from function import func
import discord
import asyncio

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

_logger = get_logger(server_id="Bot", source="llm.tools.music")

class MusicTools:
    """Tools for interacting with the Music bot features."""

    def __init__(self, runtime: "OrchestratorRequest"):
        self.runtime = runtime
        self.logger = getattr(self.runtime, "logger", _logger)

    def get_tools(self) -> list:
        runtime = self.runtime

        @tool
        async def play_music(query: str) -> str:
            """
            Plays music based on a search query or a YouTube URL.

            Use this tool when the user asks to play a song, start music, or
            provides a song name/link.

            Args:
                query: The song name or YouTube URL to play.
            """
            bot = getattr(runtime, "bot", None)
            if not bot:
                return "Error: Bot runtime is not available."

            cog = bot.get_cog("YTMusic")
            if not cog:
                return "Error: Music system (YTMusic) is not loaded."

            message = getattr(runtime, "message", None)
            if not message or not message.guild or not isinstance(message.author, discord.Member):
                return "Error: Must be used in a server."

            # Check if user is in voice channel
            if not message.author.voice:
                return "Error: User is not in a voice channel. Tell them to join one first."

            try:
                # We need an interaction to call play. Let's create a dummy one
                # The _create_dummy_interaction is available on the cog
                dummy_interaction = await cog._create_dummy_interaction(
                    message.channel, message.guild, message
                )

                # We need to adapt it since the method expects an original_interaction
                # We'll just patch the dummy interaction response methods to use the message channel
                class DummyResponse:
                    def __init__(self):
                        self.is_done = lambda: True
                    async def send_message(self, *args, **kwargs):
                        pass
                    async def defer(self, *args, **kwargs):
                        pass

                dummy_interaction.response = DummyResponse()

                class DummyFollowup:
                    async def send(self, content=None, embed=None, *args, **kwargs):
                        # Capture output to return to LLM
                        result = content or (embed.title if embed else "Action completed.")
                        return result

                dummy_interaction.followup = DummyFollowup()

                # Connect to VC if needed
                voice_client = message.guild.voice_client
                if voice_client is None:
                    await message.author.voice.channel.connect()

                if "youtube.com" in query or "youtu.be" in query:
                    if "list=" in query:
                        # Schedule playlist handling
                        asyncio.create_task(cog._handle_playlist(dummy_interaction, query))
                        return f"Added playlist to queue: {query}"
                    else:
                        success = await cog._handle_single_video(dummy_interaction, query)
                        if success:
                            return f"Added video to queue: {query}"
                        else:
                            return f"Failed to add video: {query}"
                else:
                    # Handle search
                    await cog._handle_search(dummy_interaction, query)
                    return f"Searched and added to queue: {query}"

            except Exception as e:
                # Consistent error reporting
                try:
                    await func.report_error(e, "play_music failed")
                except Exception:
                    pass
                return f"An error occurred while playing music: {e}"

        # Mark as action tool for the message agent
        play_music.__dict__["target_agent_mode"] = "message"

        return [play_music]

def get_tools(runtime: Any) -> list:
    """Return music tools."""
    return MusicTools(runtime).get_tools()
