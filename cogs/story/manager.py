import discord
from discord.ext import commands
import logging
from typing import Dict, List, Optional
import aiohttp

from .database import StoryDB
from .models import StoryInstance, StoryWorld, StoryCharacter, PlayerRelationship
from .prompt_engine import StoryPromptEngine
from .state_manager import StoryStateManager
from cogs.memory.memory_manager import MemoryManager
from gpt.gpt_response_gen import generate_response
from cogs.system_prompt.manager import SystemPromptManager

class StoryManager:
    """
    The core manager for story logic. It coordinates the database, state,
    and prompt engine to generate story progression.
    """

    def __init__(self, bot: commands.Bot, system_prompt_manager: SystemPromptManager):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.system_prompt_manager = system_prompt_manager
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

    async def _send_story_response(
        self,
        channel: discord.TextChannel,
        character: Optional[StoryCharacter],
        story_instance: StoryInstance,
        content: str,
    ):
        """
        Constructs and sends the story response as an embed, using a webhook if available.
        """
        db = self._get_db(channel.guild.id)
        embed = discord.Embed(description=content, color=discord.Color.blurple())

        # Add world state fields
        embed.add_field(name="📍 地點", value=story_instance.current_location or "未知", inline=True)
        embed.add_field(name="📅 日期", value=story_instance.current_date or "未知", inline=True)
        embed.add_field(name="⏰ 時間", value=story_instance.current_time or "未知", inline=True)

        # Fetch and add player relationships
        relationships = db.get_relationships_for_story(story_instance.channel_id)
        if relationships:
            relationship_lines = []
            for rel in relationships:
                char = db.get_character(rel.character_id)
                try:
                    user = await self.bot.fetch_user(rel.user_id)
                    user_name = user.display_name
                except discord.NotFound:
                    user_name = f"用戶(ID:{rel.user_id})"
                
                if char:
                    relationship_lines.append(f"**{user_name}** 與 **{char.name}**: {rel.description}")

            if relationship_lines:
                embed.add_field(
                    name="🤝 人際關係",
                    value="\n".join(relationship_lines),
                    inline=False,
                )

        # Send the message
        if character and character.webhook_url:
            try:
                async with aiohttp.ClientSession() as session:
                    webhook = discord.Webhook.from_url(character.webhook_url, session=session)
                    avatar_url = character.attributes.get("image_url")
                    await webhook.send(
                        embed=embed,
                        username=character.name,
                        avatar_url=avatar_url,
                    )
            except Exception as e:
                self.logger.error(f"Webhook send failed for character {character.name}: {e}. Falling back to channel.send.")
                await channel.send(embed=embed)
        else:
            await channel.send(embed=embed)

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
        story_instance = db.get_story_instance(channel_id)
        if not story_instance:
            await message.reply("這個頻道還沒有開始任何故事！請管理員使用 `/story start` 來開啟一段新的冒險。")
            return
        
        if not story_instance.is_active:
            await message.reply("這個頻道的故事已經結束了。")
            return

        world = db.get_world(story_instance.world_name)
        if not world:
            await message.reply(f"錯誤：找不到與此故事關聯的世界 `{story_instance.world_name}`。")
            return
            
        # Load active characters for this story
        characters: List[StoryCharacter] = []
        for character_id in story_instance.active_characters:
            character = db.get_character(character_id)
            if character:
                characters.append(character)

        self.logger.info(f"Processing story message for instance in channel {channel_id} (World: {story_instance.world_name})")
        
        async with message.channel.typing():
            # 2. Build prompt using PromptEngine
            relationships = db.get_relationships_for_story(channel_id)
            prompt = await self.prompt_engine.build_story_prompt(
                instance=story_instance,
                world=world,
                characters=characters,
                relationships=relationships,
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


            # 6. Determine speaking character and send response
            speaking_character: Optional[StoryCharacter] = None
            response_content = llm_response

            # Check if the response is from a specific character
            for char in characters:
                if llm_response.startswith(f"{char.name}：") or llm_response.startswith(f"{char.name}:"):
                    speaking_character = char
                    # Strip character name and colon from the content
                    temp_content = llm_response[len(char.name):].lstrip()
                    if temp_content.startswith((':', '：')):
                        response_content = temp_content[1:].lstrip()
                    else:
                        response_content = temp_content
                    break
            
            await self._send_story_response(
                channel=message.channel,
                character=speaking_character,
                story_instance=updated_instance,
                content=response_content,
            )