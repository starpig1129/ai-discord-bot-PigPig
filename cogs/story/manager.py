import discord
from discord.ext import commands
import logging
from typing import Dict, List, Optional
import aiohttp
import json
import datetime
from pydantic import ValidationError

from .database import StoryDB, CharacterDB
from .models import StoryInstance, StoryWorld, StoryCharacter, PlayerRelationship, Event, Location
from .prompt_engine import StoryPromptEngine, GMActionPlan, RelationshipUpdate
from .state_manager import StoryStateManager
from cogs.memory.memory_manager import MemoryManager
from gpt.gemini_api import generate_response_with_cache, generate_structured_response, GeminiError
from cogs.system_prompt.manager import SystemPromptManager


class StoryManager:
    """
    The core manager for story logic. It coordinates the database, state,
    and prompt engine to generate story progression based on the v5 layered AI agent architecture.
    """

    def __init__(self, bot: commands.Bot, system_prompt_manager: SystemPromptManager):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.system_prompt_manager = system_prompt_manager
        self._initialized = False
        self.db_instances: Dict[int, StoryDB] = {}
        self.character_db = CharacterDB()
        self.prompt_engine = StoryPromptEngine(bot)
        self.memory_manager: MemoryManager = self.bot.memory_manager
        self.state_manager = StoryStateManager(bot)

    def _get_db(self, guild_id: int) -> StoryDB:
        """Gets or creates a database connection for a specific guild."""
        if guild_id not in self.db_instances:
            self.db_instances[guild_id] = StoryDB(guild_id)
            self.db_instances[guild_id].initialize()
        return self.db_instances[guild_id]

    async def initialize(self):
        """
        Initializes the StoryManager and its components.
        """
        self.character_db.initialize()
        self._initialized = True
        self.logger.info("StoryManager initialized.")

    async def _update_relationships(self, db: StoryDB, story_id: int, updates: List[RelationshipUpdate]):
        """Updates player-NPC relationships based on the GM plan."""
        if not updates:
            return
        
        self.logger.info(f"Updating {len(updates)} relationships for story {story_id}.")
        
        # Fetch all characters and relationships once to avoid multiple DB calls in a loop.
        all_characters_in_guild = self.character_db.get_characters_by_guild(db.guild_id)
        all_relationships_in_story = db.get_relationships_for_story(story_id)

        for update in updates:
            try:
                # Find user by display name (this part is okay, but has its own limitations).
                user = discord.utils.find(lambda u: u.display_name == update.user_name, self.bot.users)
                if not user:
                    self.logger.warning(f"Could not find user by display name: {update.user_name}")
                    continue

                # Find character by name from the pre-fetched list.
                char = next((c for c in all_characters_in_guild if c.name == update.character_name), None)
                if not char:
                    self.logger.warning(f"Could not find character by name: {update.character_name}")
                    continue

                # Find relationship from the pre-fetched list.
                relationship = next((r for r in all_relationships_in_story if r.user_id == user.id and r.character_id == char.character_id), None)
                
                if relationship:
                    relationship.description = update.description
                    db.save_player_relationship(relationship)
                else:
                    new_rel = PlayerRelationship(
                        story_id=story_id,
                        character_id=char.character_id,
                        user_id=user.id,
                        description=update.description
                    )
                    db.save_player_relationship(new_rel)
            except Exception as e:
                self.logger.error(f"Failed to update relationship for {update.character_name}: {e}", exc_info=True)

    async def _record_event(self, db: StoryDB, world: StoryWorld, instance: StoryInstance, gm_plan: GMActionPlan, final_content: str):
        """Creates and records an event in the world state."""
        current_location_obj = next((loc for loc in world.locations if loc.name == instance.current_location), None)
        
        if not current_location_obj:
            self.logger.warning(f"Location '{instance.current_location}' not found in world '{world.world_name}' for event recording.")
            # As a fallback, create the location if it doesn't exist.
            current_location_obj = Location(name=instance.current_location)
            world.locations.append(current_location_obj)

        event = Event(
            title=gm_plan.event_title,
            summary=gm_plan.event_summary,
            full_content=final_content,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        current_location_obj.events.append(event)
        
        # Note: This assumes `save_world` is capable of serializing the entire world object,
        # including nested locations and events. The database schema might need adjustments.
        db.save_world(world)
        self.logger.info(f"Recorded event '{event.title}' in '{world.world_name}/{instance.current_location}'.")


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
                char = self.character_db.get_character(rel.character_id)
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
        Processes a message from a story channel using the v5 layered agent architecture.
        This method acts as the central orchestrator.
        """
        if not self._initialized:
            self.logger.warning("StoryManager not initialized, skipping message.")
            return

        guild_id = message.guild.id
        channel_id = message.channel.id
        db = self._get_db(guild_id)

        story_instance = db.get_story_instance(channel_id)
        if not story_instance or not story_instance.is_active:
            return

        world = db.get_world(story_instance.world_name)
        if not world:
            await message.reply(f"錯誤：找不到世界 `{story_instance.world_name}`。")
            return

        characters = [char for char_id in story_instance.active_character_ids if (char := self.character_db.get_character(char_id))]
        self.logger.info(f"V5 Orchestrator: Processing message in c:{channel_id} w:{world.world_name}")

        async with message.channel.typing():
            try:
                # --- Step 1: Call GM Agent for a structured plan ---
                gm_prompt = await self.prompt_engine.build_gm_prompt(story_instance, world, characters, message.content)
                
                # Use the new structured response function to get the GM plan directly.
                gm_plan = await generate_structured_response(
                    inst=gm_prompt,
                    system_prompt="You are a helpful storytelling assistant. Your output MUST be a single, valid JSON object that conforms to the requested schema.",
                    response_schema=GMActionPlan
                )

                # --- Step 2: The GM Action Plan is already parsed ---
                if not gm_plan:
                    # Handle cases where the response could not be parsed or is empty
                    raise GeminiError("Failed to generate a valid GM action plan.")

                response_content = ""
                speaking_character: Optional[StoryCharacter] = None

                # --- Step 3: Execute the plan (NARRATE or DIALOGUE) ---
                if gm_plan.action_type == "NARRATE":
                    self.logger.info(f"GM Action: NARRATE. Event: {gm_plan.event_title}")
                    response_content = gm_plan.narration_content
                
                elif gm_plan.action_type == "DIALOGUE":
                    self.logger.info(f"GM Action: DIALOGUE for {gm_plan.dialogue_context.speaker_name}. Event: {gm_plan.event_title}")
                    
                    # --- Step 3B: Call Character Agent ---
                    speaker_name = gm_plan.dialogue_context.speaker_name
                    speaking_character = next((c for c in characters if c.name == speaker_name), None)

                    if speaking_character:
                        # Step 3B: Build separated prompts and call Character Agent
                        char_system_prompt, char_user_prompt = await self.prompt_engine.build_character_prompt(
                            character=speaking_character,
                            gm_context=gm_plan.dialogue_context.model_dump(),
                        )
                        
                        _, char_response_gen = await generate_response_with_cache(
                            inst=char_user_prompt,
                            system_prompt=char_system_prompt,
                        )
                        
                        response_content = "".join([chunk async for chunk in char_response_gen]).strip()
                    else:
                        self.logger.warning(f"Character '{speaker_name}' not found for dialogue.")
                        response_content = f"({speaker_name} 想要說話，但似乎走神了...)"

                # --- Step 4: Update World State & Relationships ---
                updated_instance = await self.state_manager.update_state_from_gm_plan(story_instance, gm_plan)
                await self._update_relationships(db, updated_instance.channel_id, gm_plan.relationships_update)
                
                # --- Step 5: Record Event ---
                await self._record_event(db, world, updated_instance, gm_plan, response_content)
                
                # Save the final state of the instance after all updates
                db.save_story_instance(updated_instance)

                # --- Step 6: Send Response to User ---
                await self._send_story_response(
                    channel=message.channel,
                    character=speaking_character,
                    story_instance=updated_instance,
                    content=response_content,
                )

            except (GeminiError, json.JSONDecodeError, ValidationError) as e:
                self.logger.error(f"Error in V5 story generation pipeline: {e}", exc_info=True)
                await message.reply("故事之神的大腦似乎纏在一起了，祂需要一點時間來解開... 請稍後再試。")
            except Exception as e:
                self.logger.error(f"An unexpected error occurred in V5 story generation: {e}", exc_info=True)
                await message.reply("一陣無法預測的宇宙射線干擾了故事的進行，請稍後再試...")