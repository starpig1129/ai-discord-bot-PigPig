import discord
from discord.ext import commands
import logging
from typing import Dict, List

from .database import StoryDB
from .models import StoryInstance, StoryWorld, StoryCharacter
from .prompt_engine import StoryPromptEngine
from .state_manager import StoryStateManager
from cogs.memory.memory_manager import MemoryManager
from gpt.gpt_response_gen import generate_response

class StoryManager:
    """
    The core manager for story logic. It coordinates the database, state, 
    and prompt engine to generate story progression.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self._initialized = False
        self.db_instances: Dict[int, StoryDB] = {}
        self.prompt_engine = StoryPromptEngine(bot)
        self.memory_manager: MemoryManager = self.bot.memory_manager
        self.state_manager = StoryStateManager(bot)

    def _get_db(self, guild_id: int) -> StoryDB:
        """Gets or creates a database connection for a specific guild."""
        if guild_id not in self.db_instances:
            self.db_instances[guild_id] = StoryDB(guild_id)
        return self.db_instances[guild_id]

    async def initialize(self):
        """
        Initializes the StoryManager and its components.
        """
        self._initialized = True
        self.logger.info("StoryManager initialized.")

    async def process_story_message(self, message: discord.Message):
        """
        Processes a message from a story channel.
        This is the entry point for the main story generation loop.
        """
        if not self._initialized:
            self.logger.warning("StoryManager is not initialized. Cannot process message.")
            return

        guild_id = message.guild.id
        channel_id = message.channel.id
        db = self._get_db(guild_id)

        # 1. Get StoryInstance and related data
        story_instance = await db.get_story_instance(channel_id)
        if not story_instance:
            await message.reply("這個頻道還沒有開始任何故事！請管理員使用 `/story start` 來開啟一段新的冒險。")
            return
        
        if not story_instance.is_active:
            await message.reply("這個頻道的故事已經結束了。")
            return

        world = await db.get_world(story_instance.world_name)
        if not world:
            await message.reply(f"錯誤：找不到與此故事關聯的世界 `{story_instance.world_name}`。")
            return
            
        # Load active characters for this story
        characters: List[StoryCharacter] = []
        for character_id in story_instance.active_characters:
            character = await db.get_character(character_id)
            if character:
                characters.append(character)

        self.logger.info(f"Processing story message for instance in channel {channel_id} (World: {story_instance.world_name})")
        
        async with message.channel.typing():
            # 2. Build prompt using PromptEngine
            prompt = await self.prompt_engine.build_story_prompt(
                instance=story_instance,
                world=world,
                characters=characters,
                user_input=message.content
            )

            # 3. Call LLM using the unified generate_response function
            try:
                # Use the generate_response function directly from gpt_response_gen
                thread, response_generator = await generate_response(
                    inst=prompt,
                    system_prompt="You are a helpful storytelling assistant.",
                    dialogue_history=[]
                )
                
                # Collect the full response from the generator
                response_parts = []
                async for chunk in response_generator:
                    response_parts.append(chunk)
                
                llm_response = "".join(response_parts)

            except Exception as e:
                self.logger.error(f"Error calling LLM for story generation: {e}", exc_info=True)
                await message.reply("故事之神打盹了，請稍後再試...")
                return

            # 4. Update state using StateManager
            story_instance.event_log.append(f"User ({message.author.display_name}): {message.content}")
            updated_instance = await self.state_manager.update_state_from_llm(story_instance, llm_response)
            db.save_story_instance(updated_instance)

            # 5. Store event summary in MemoryManager
            if self.memory_manager and self.memory_manager.is_enabled:
                # Create a "fake" message object to store the event summary
                event_summary = f"In the world of {world.world_name}, the user '{message.author.display_name}' did: '{message.content}'. The outcome was: '{llm_response}'"
                
                # We need a way to create a message-like object or adapt store_message
                # For now, let's assume we can store raw text with metadata.
                # This part needs to be coordinated with the MemoryManager's capabilities.
                # Let's log it for now.
                self.logger.info(f"Would store to memory: {event_summary}")


            # 6. Send response
            await message.reply(llm_response)