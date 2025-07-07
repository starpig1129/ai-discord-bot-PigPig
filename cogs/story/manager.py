import discord
from discord.ext import commands
import logging
from typing import Dict, List, Optional
import aiohttp
import json
from pydantic import ValidationError

from .database import StoryDB, CharacterDB
from .models import StoryInstance, StoryWorld, StoryCharacter, PlayerRelationship, Event, Location, GMActionPlan, RelationshipUpdate, CharacterAction
from .prompt_engine import StoryPromptEngine
from .state_manager import StoryStateManager
from cogs.memory.memory_manager import MemoryManager
from gpt.gemini_api import generate_response_with_cache, GeminiError
from cogs.system_prompt.manager import SystemPromptManager


class StoryManager:
    """
    The core manager for story logic. It coordinates the database, state,
    and prompt engine to generate story progression based on the v5 layered AI agent architecture.
    """

    def __init__(self, bot: commands.Bot, cog: commands.Cog, system_prompt_manager: SystemPromptManager):
        self.bot = bot
        self.cog = cog
        self.logger = logging.getLogger(__name__)
        self.system_prompt_manager = system_prompt_manager
        self._initialized = False
        self.db_instances: Dict[int, StoryDB] = {}
        self.character_db = CharacterDB()
        self.prompt_engine = StoryPromptEngine(self.bot, self.system_prompt_manager)
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

        # The event's timestamp should reflect the in-story time, not real-world time.
        event_timestamp = f"{instance.current_date} {instance.current_time}"

        event = Event(
            title=gm_plan.event_title,
            summary=gm_plan.event_summary,
            full_content=final_content,
            timestamp=event_timestamp
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
        content: str | CharacterAction,
    ):
        """
        Constructs and sends the story response as an embed, using a webhook if available.
        """
        db = self._get_db(channel.guild.id)
        
        description = ""
        if isinstance(content, CharacterAction):
            parts = []
            if content.action:
                parts.append(f"*{content.action}*")
            parts.append(content.dialogue)
            if content.thought:
                parts.append(f"\n💭 {content.thought}")
            description = "\n".join(parts)
        else:
            description = content

        embed = discord.Embed(description=description, color=discord.Color.blurple())

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
                gm_prompt = await self.prompt_engine.build_gm_prompt(
                    instance=story_instance,
                    world=world,
                    characters=characters,
                    user_input=message.content,
                    story_outlines=story_instance.outlines
                )

                # Prepare dialogue history for the GM, treating each outline and summary as a separate piece of context
                gm_dialogue_history = []
                if story_instance.outlines:
                    for outline in story_instance.outlines:
                        gm_dialogue_history.append({
                            "role": "user",
                            "content": f"High-level story outline: {outline}"
                        })
                if story_instance.summaries:
                    for summary in story_instance.summaries[-5:]:
                        gm_dialogue_history.append({
                            "role": "user",
                            "content": f"Recent plot summary: {summary}"
                        })

                # Use the new structured response function to get the GM plan directly.
                _, gm_plan = await generate_response_with_cache(
                    inst=message.content,
                    system_prompt=gm_prompt,
                    dialogue_history=gm_dialogue_history,
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
                        # Fetch recent conversation history
                        history_messages = [msg async for msg in message.channel.history(limit=20)]
                        history_messages.reverse()  # Oldest to newest
                        
                        # Build the dialogue history for the character, starting with summaries
                        dialogue_history = []
                        if story_instance.summaries:
                            for summary in story_instance.summaries[-5:]:
                                dialogue_history.append({
                                    "role": "user",
                                    "content": f"[Contextual Summary: {summary}]"
                                })

                        # Append recent conversation messages
                        for msg in history_messages:
                            content = msg.content
                            role = "user"  # Default to user

                            if msg.author.id == self.bot.user.id and msg.embeds:
                                content = msg.embeds[0].description or ""
                                role = "assistant"
                            elif msg.author.id != self.bot.user.id:
                                role = "user"

                            if content.strip():
                                dialogue_history.append({"role": role, "content": content})

                        # Step 3B: Build separated prompts and call Character Agent
                        char_system_prompt, char_user_prompt = await self.prompt_engine.build_character_prompt(
                            character=speaking_character,
                            gm_context=gm_plan.dialogue_context,
                            guild_id=guild_id
                        )
                        
                        _, character_action = await generate_response_with_cache(
                            inst=char_user_prompt,
                            system_prompt=char_system_prompt,
                            dialogue_history=dialogue_history,
                            response_schema=CharacterAction
                        )
                        
                        response_content = character_action
                    else:
                        self.logger.warning(f"Character '{speaker_name}' not found for dialogue.")
                        response_content = f"({speaker_name} 想要說話，但似乎走神了...)"

                # --- Step 4: Update World State & Relationships ---
                updated_instance = await self.state_manager.update_state_from_gm_plan(story_instance, gm_plan)
                await self._update_relationships(db, updated_instance.channel_id, gm_plan.relationships_update)
                
                # --- Step 5: Record Event ---
                # Ensure we log the string representation for the event record.
                if isinstance(response_content, CharacterAction):
                    event_text = f"{response_content.action or ''} {response_content.dialogue} {response_content.thought or ''}".strip()
                else:
                    event_text = response_content
                await self._record_event(db, world, updated_instance, gm_plan, event_text)
                
                # --- Step 5.5: Handle Summary Generation ---
                updated_instance.message_counter += 1
                if updated_instance.message_counter >= 20:
                    self.logger.info(f"Message counter reached {updated_instance.message_counter}, generating summary for story {updated_instance.channel_id}")
                    await self._generate_and_save_summary(updated_instance)
                    # The summary function will reset the counter and save the instance
                else:
                    # Save the instance if no summary was generated
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

    async def _generate_and_save_summary(self, story_instance: StoryInstance):
        """
        Generates a summary of the last 20-40 messages and saves it.
        """
        db = self._get_db(story_instance.guild_id)
        channel = self.bot.get_channel(story_instance.channel_id)
        if not channel:
            self.logger.error(f"Cannot generate summary, channel {story_instance.channel_id} not found.")
            return

        self.logger.info(f"Generating summary for story in channel {channel.id}")
        try:
            # Fetch last 30 messages for context
            history_messages = [msg async for msg in channel.history(limit=30)]
            history_messages.reverse()

            # Format history into the required List[Dict[str, str]] format
            dialogue_history = []
            for msg in history_messages:
                content = msg.content
                role = "user"
                if msg.author.id == self.bot.user.id and msg.embeds:
                    content = msg.embeds[0].description or ""
                    role = "assistant"
                elif msg.author.id != self.bot.user.id:
                    role = "user"
                
                if content.strip():
                    dialogue_history.append({"role": role, "content": content})
            
            if not dialogue_history:
                self.logger.info("No content to summarize.")
                story_instance.message_counter = 0
                db.save_story_instance(story_instance)
                return

            summary_system_prompt = (
                "You are a story summarization assistant. "
                "Based on the provided conversation log, please provide a concise, one-paragraph summary. "
                "Focus on key events, character actions, and significant plot developments. "
                "The summary should capture the essence of what happened, serving as a memory for the AI. "
                "Do not add any introductory or concluding phrases."
            )
            
            summary_inst = "Please provide a concise, one-paragraph summary of the preceding conversation."

            _, summary_gen = await generate_response_with_cache(
                inst=summary_inst,
                system_prompt=summary_system_prompt,
                dialogue_history=dialogue_history,
            )
            
            summary_text = "".join([chunk async for chunk in summary_gen]).strip()

            if summary_text:
                story_instance.summaries.append(summary_text)
                self.logger.info(f"Generated and saved new summary for story {story_instance.channel_id}. Total summaries: {len(story_instance.summaries)}")
                
                # Check if it's time to generate an outline
                if len(story_instance.summaries) > 0 and len(story_instance.summaries) % 10 == 0:
                    self.logger.info(f"Summary count is a multiple of 10. Generating outline for story {story_instance.channel_id}.")
                    await self._generate_and_save_outline(story_instance)
            else:
                self.logger.warning(f"Summary generation resulted in empty text for story {story_instance.channel_id}.")

        except Exception as e:
            self.logger.error(f"Failed to generate summary for story {story_instance.channel_id}: {e}", exc_info=True)
        finally:
            # Reset counter and save the instance regardless of success or failure
            story_instance.message_counter = 0
            db.save_story_instance(story_instance)

    async def _generate_and_save_outline(self, story_instance: StoryInstance):
        """
        Generates a high-level outline from the last 10 summaries and saves it.
        """
        self.logger.info(f"Attempting to generate outline for story {story_instance.channel_id}.")

        # Ensure there are enough summaries
        if len(story_instance.summaries) < 10:
            self.logger.warning(f"Not enough summaries to generate an outline for story {story_instance.channel_id}. Need 10, have {len(story_instance.summaries)}.")
            return

        # Get the most recent 10 summaries
        recent_summaries = story_instance.summaries[-10:]
        formatted_summaries = "\n".join([f"{i+1}. {s}" for i, s in enumerate(recent_summaries)])

        outline_system_prompt = (
            "You are a master storyteller and editor. "
            "Based on the provided plot summaries, please synthesize them into a single, high-level outline paragraph. "
            "This outline should capture the major story arc, character progressions, and key turning points. "
            "Focus on the overarching narrative, omitting minor details. "
            "The goal is to create a concise, big-picture view of the story so far for the Director AI. "
            "Do not add any introductory or concluding phrases."
        )
        
        outline_inst = "Based on the following 10 plot summaries, please synthesize them into a single, high-level outline paragraph."
        
        # Format summaries into the dialogue history structure
        dialogue_history = [{'role': 'user', 'content': f"## Recent Plot Summaries\n{formatted_summaries}"}]

        try:
            _, outline_gen = await generate_response_with_cache(
                inst=outline_inst,
                system_prompt=outline_system_prompt,
                dialogue_history=dialogue_history,
            )
            
            outline_text = "".join([chunk async for chunk in outline_gen]).strip()

            if outline_text:
                story_instance.outlines.append(outline_text)
                self.logger.info(f"Generated and saved new outline for story {story_instance.channel_id}. Total outlines: {len(story_instance.outlines)}")
            else:
                self.logger.warning(f"Outline generation resulted in empty text for story {story_instance.channel_id}.")

        except Exception as e:
            self.logger.error(f"Failed to generate outline for story {story_instance.channel_id}: {e}", exc_info=True)
        # The instance will be saved in the finally block of _generate_and_save_summary

    async def start_story(
        self,
        interaction: discord.Interaction,
        world_name: str,
        character_ids: List[str],
        use_narrator: bool,
        initial_date: Optional[str],
        initial_time: Optional[str],
        initial_location: str
    ):
        """
        Handles the logic of starting a new story, creating the instance,
        and generating the first scene.
        """
        db = self._get_db(interaction.guild_id)
        world = db.get_world(world_name)
        if not world:
            self.logger.error(f"FATAL: Could not find world '{world_name}' during story start.")
            await interaction.edit_original_response(content="❌ 無法載入世界資料，故事無法開始。", embed=None, view=None)
            return

        if use_narrator:
            # This is the standard path with a narrator
            self.logger.info(f"Starting story '{world_name}' with narrator.")
            story_instance = StoryInstance(
                channel_id=interaction.channel_id,
                guild_id=interaction.guild_id,
                world_name=world_name,
                current_date=initial_date,
                current_time=initial_time,
                current_location=initial_location,
                active_character_ids=character_ids,
                is_active=True
            )
            # Save the story instance to database
            db.save_story_instance(story_instance)
            await self.generate_first_scene(interaction, story_instance)

        else:
            # This is the path we need to investigate
            self.logger.info("Entering 'use_narrator=False' logic branch.")
            
            self.logger.info(f"Received character_ids: {character_ids}")
            all_selected_chars = self.character_db.get_characters_by_ids(character_ids)
            self.logger.info(f"Fetched {len(all_selected_chars)} character objects from the database.")

            if not all_selected_chars:
                self.logger.error("Error: No character objects were fetched despite receiving IDs.")
                await interaction.edit_original_response(content="❌ 錯誤：選擇的角色無法載入，故事無法開始。", embed=None, view=None)
                return

            director_character = all_selected_chars[0]
            self.logger.info(f"Designated director: {director_character.name} (ID: {director_character.character_id})")

            actor_characters = all_selected_chars[1:]
            self.logger.info(f"Designated {len(actor_characters)} actors.")

            self.logger.info("Preparing to create StoryInstance...")
            story_instance = StoryInstance(
                channel_id=interaction.channel_id,
                guild_id=interaction.guild_id,
                world_name=world_name,
                current_date=initial_date,
                current_time=initial_time,
                current_location=initial_location,
                active_character_ids=character_ids,
                is_active=True
            )
            # Save the story instance to database
            db.save_story_instance(story_instance)
            self.logger.info(f"Successfully created story_instance for channel: {story_instance.channel_id}")

            self.logger.info("Preparing to call self.generate_first_scene...")
            await self.generate_first_scene(interaction, story_instance)
            self.logger.info("Successfully completed call to generate_first_scene.")

    async def generate_first_scene(self, interaction: discord.Interaction, story_instance: StoryInstance):
        """
        Generates the introductory scene for a new story using the v5 architecture.
        """
        self.logger.info(f"V5: Generating first scene for story in channel {interaction.channel_id}")
        db = self._get_db(interaction.guild.id)
        world = db.get_world(story_instance.world_name)
        
        async with interaction.channel.typing():
            try:
                # --- Step 1: Build the prompt for the GM to start the story ---
                characters = self.character_db.get_characters_by_ids(story_instance.active_character_ids)
                gm_prompt = await self.prompt_engine.build_story_start_prompt(story_instance, world, characters)

                # --- Step 2: Call GM Agent for a structured plan ---
                _, gm_plan = await generate_response_with_cache(
                    inst=gm_prompt,
                    system_prompt="You are a helpful storytelling assistant. Your output MUST be a single, valid JSON object that conforms to the requested schema.",
                    response_schema=GMActionPlan
                )

                # Defensive coding: Handle if the API returns a generator function due to hot-reload issues
                if callable(gm_plan):
                    self.logger.warning("GM plan is a callable, processing as a stream.")
                    full_response_text = "".join([chunk async for chunk in gm_plan()])
                    
                    # Manually parse the JSON string to the Pydantic model
                    try:
                        gm_plan = GMActionPlan.model_validate_json(full_response_text)
                        self.logger.info("Successfully parsed streamed response into GMActionPlan.")
                    except Exception as e:
                        raise GeminiError(f"Failed to parse streamed JSON response: {e}\nContent: {full_response_text}")

                if not gm_plan or gm_plan.action_type != "NARRATE" or not gm_plan.narration_content:
                    raise GeminiError("Failed to generate a valid opening narration plan.")

                # --- Step 3: Update World State & Relationships (if any) ---
                updated_instance = await self.state_manager.update_state_from_gm_plan(story_instance, gm_plan)
                await self._update_relationships(db, updated_instance.channel_id, gm_plan.relationships_update)

                # --- Step 4: Record the opening event ---
                await self._record_event(db, world, updated_instance, gm_plan, gm_plan.narration_content)
                
                # Save the final state of the instance
                db.save_story_instance(updated_instance)

                # --- Step 5: Send the opening narration to the channel ---
                await self._send_story_response(
                    channel=interaction.channel,
                    character=None,  # Narrator speaks first
                    story_instance=updated_instance,
                    content=gm_plan.narration_content,
                )

                # --- Step 6: Finalize the public "Story Started" message ---
                embed = discord.Embed(
                    title="🎬 故事開始！",
                    description=f"**{world.world_name}** 的冒險篇章已在此頻道開啟！",
                    color=discord.Color.gold()
                )
                world_background = world.attributes.get('background', '這個世界沒有背景描述。')
                embed.add_field(name="🌍 世界背景", value=world_background[:800] + ("..." if len(world_background) > 800 else ""), inline=False)
                embed.add_field(name="📅 日期", value=updated_instance.current_date, inline=True)
                embed.add_field(name="⏰ 時間", value=updated_instance.current_time, inline=True)
                embed.add_field(name="📍 地點", value=updated_instance.current_location, inline=False)
                
                characters = [self.character_db.get_character(cid) for cid in updated_instance.active_character_ids]
                if characters:
                    selected_npcs = [char.name for char in characters if char]
                    embed.add_field(name="👥 參與的NPC", value=", ".join(selected_npcs) if selected_npcs else "無", inline=False)

                embed.set_footer(text="💡 在此頻道輸入訊息來與故事互動")
                
                await interaction.edit_original_response(content=None, embed=embed, view=None)
                self.logger.info(f"V5 story started successfully in channel {interaction.channel_id}")

            except (GeminiError, json.JSONDecodeError, ValidationError) as e:
                self.logger.error(f"Error in V5 first scene generation: {e}", exc_info=True)
                await interaction.edit_original_response(content="❌ 故事開始了，但開場白被一陣神秘的靜電干擾了...", embed=None, view=None)
            except Exception as e:
                self.logger.error(f"An unexpected error occurred in V5 first scene generation: {e}", exc_info=True)
                await interaction.edit_original_response(content="一陣無法預測的宇宙射線干擾了故事的進行，請稍後再試...", embed=None, view=None)