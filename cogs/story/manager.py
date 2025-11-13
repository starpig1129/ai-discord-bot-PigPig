import discord
from discord.ext import commands
import logging
import random
from typing import Dict, List, Optional, Any, cast
import aiohttp
import json
from pydantic import ValidationError
import re
from function import func

from llm.model_manager import ModelManager
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from .database import StoryDB, CharacterDB
from .models import StoryInstance, StoryWorld, StoryCharacter, PlayerRelationship, Event, Location, GMActionPlan, RelationshipUpdate, CharacterAction
from .prompt_engine import StoryPromptEngine
from .state_manager import StoryStateManager
from cogs.system_prompt.manager import SystemPromptManager
from cogs.language_manager import LanguageManager
from .ui.modals import InterventionModal


_ALLOWED_MENTIONS = discord.AllowedMentions(
    users=True,
    roles=False,
    everyone=False,
    replied_user=True
)

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
        self.state_manager = StoryStateManager(bot)
        self.language_manager: LanguageManager = cast(LanguageManager, self.bot.get_cog("LanguageManager"))
        self.interventions: Dict[int, str] = {}

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

    def add_intervention(self, channel_id: int, text: str):
        """Stores an intervention for a specific channel."""
        self.interventions[channel_id] = text
        self.logger.info(f"Intervention added for channel {channel_id}.")

    async def intervene(self, interaction: discord.Interaction):
        """
        Opens a modal for the user to provide an OOC intervention.
        """
        # Ensure the story is active in the current channel
        assert interaction.guild_id is not None, "interaction.guild_id must not be None"
        assert interaction.channel_id is not None, "interaction.channel_id must not be None"
        db = self._get_db(cast(int, interaction.guild_id))
        story_instance = db.get_story_instance(cast(int, interaction.channel_id))
        if not story_instance or not story_instance.is_active:
            await interaction.response.send_message(
                "❌ 此頻道沒有正在進行的故事，無法進行干預。",
                ephemeral=True,
                allowed_mentions=_ALLOWED_MENTIONS
            )
            return
            
        modal = InterventionModal(self)
        await interaction.response.send_modal(modal)

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

        if isinstance(content, CharacterAction):
            # For character actions, set the footer with their specific time and location
            footer_text = f"📍 {content.location}  |  📅 {content.date}  |  ⏰ {content.time}"
            embed.set_footer(text=footer_text)
        else:
            # For narrations, use the general story instance state in fields
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
                        allowed_mentions=_ALLOWED_MENTIONS,
                    )
            except Exception as e:
                self.logger.error(f"Webhook send failed for character {character.name}: {e}. Falling back to channel.send.")
                await channel.send(embed=embed, allowed_mentions=_ALLOWED_MENTIONS)
        else:
            await channel.send(embed=embed, allowed_mentions=_ALLOWED_MENTIONS)

    async def process_story_message(self, message: discord.Message):
        """
        Processes a message from a story channel using the v5 layered agent architecture.
        This method acts as the central orchestrator.
        """
        if not self._initialized:
            self.logger.warning("StoryManager not initialized, skipping message.")
            return

        assert message.guild is not None, "message.guild must not be None"
        guild_id = cast(int, message.guild.id)
        channel_id = cast(int, message.channel.id)
        assert self.bot.user is not None, "bot.user must not be None"
        bot_user_id = cast(int, self.bot.user.id)
        db = self._get_db(guild_id)

        story_instance = db.get_story_instance(channel_id)
        if not story_instance or not story_instance.is_active:
            return

        world = db.get_world(story_instance.world_name)
        if not world:
            await message.reply(f"錯誤：找不到世界 `{story_instance.world_name}`。", allowed_mentions=_ALLOWED_MENTIONS)
            return

        characters = [char for char_id in story_instance.active_character_ids if (char := self.character_db.get_character(char_id))]
        self.logger.info(f"V5 Orchestrator: Processing message in c:{channel_id} w:{world.world_name}")

        async with cast(discord.TextChannel, message.channel).typing():
            try:
                # --- Step 1: Call GM Agent for a structured plan ---
                # Check for and retrieve any pending intervention for this channel
                intervention_text = self.interventions.pop(channel_id, None)
                if intervention_text:
                    self.logger.info(f"Applying intervention for channel {channel_id}: {intervention_text}")

                language = self.language_manager.get_server_lang(str(guild_id))
                gm_prompt = await self.prompt_engine.build_gm_prompt(
                    instance=story_instance,
                    world=world,
                    characters=characters,
                    user_input=message.content,
                    story_outlines=story_instance.outlines,
                    language=language,
                    intervention_text=intervention_text,
                )

                # Prepare dialogue history for the GM, treating each outline and summary as a separate piece of context
                gm_dialogue_history = []
                if story_instance.outlines:
                    for outline in story_instance.outlines:
                        gm_dialogue_history.append(HumanMessage(
                            content=f"High-level story outline: {outline}"
                        ))
                if story_instance.summaries:
                    for summary in story_instance.summaries[-5:]:
                        gm_dialogue_history.append(HumanMessage(
                            content=f"Recent plot summary: {summary}"
                        ))

                # Call GM agent via ModelManager + LangChain create_agent
                story_gm_model, fallback = ModelManager().get_model("story_gm_model")
                agent = create_agent(story_gm_model, 
                                     tools=[], 
                                     system_prompt=gm_prompt, 
                                     response_format=GMActionPlan,
                                     middleware=[fallback])
                message_list = [HumanMessage(content=message.content)] + gm_dialogue_history
                response = await agent.ainvoke(cast(Any, {"messages": message_list}))

                # Deterministic parsing: agent MUST return a dict containing 'structured_response' or 'output' (dict or JSON string).
                try:
                    if not isinstance(response, dict):
                        raise Exception("Agent response must be a dict with 'structured_response' or 'output'")

                    resp_payload = response.get("structured_response") or response.get("output") or response.get("result")
                    if resp_payload is None:
                        raise Exception("Agent response missing 'structured_response' / 'output' / 'result' field")

                    if isinstance(resp_payload, str):
                        gm_plan = GMActionPlan.model_validate_json(resp_payload)
                    else:
                        gm_plan = GMActionPlan.model_validate(resp_payload)
                except Exception as e:
                    self.logger.error("Failed to parse GMActionPlan from agent response: %s", e)
                    try:
                        await func.report_error(e, "story.gm_action_parse_failed")
                    except Exception:
                        self.logger.exception("func.report_error failed when reporting gm_action_parse_failed")
                    raise

                # --- Step 3: Execute the plan (NARRATE or DIALOGUE) ---
                event_text_for_log = ""
                # Use deterministic baseline state; overwrite in DIALOGUE branch when provided by GM plan.
                latest_location = story_instance.current_location
                latest_date = story_instance.current_date
                latest_time = story_instance.current_time

                if gm_plan.action_type == "NARRATE":
                    self.logger.info(f"GM Action: NARRATE. Event: {gm_plan.event_title}")
                    if gm_plan.narration_content:
                        await self._send_story_response(
                            channel=cast(discord.TextChannel, message.channel),
                            character=None,
                            story_instance=story_instance, # Use pre-update instance for state display
                            content=gm_plan.narration_content,
                        )
                        event_text_for_log = gm_plan.narration_content
                    else:
                        self.logger.info("Narration is disabled or was not generated. No message sent.")
                        event_text_for_log = f"({gm_plan.event_summary})" # Log summary if no narration
                
                elif gm_plan.action_type == "DIALOGUE":
                    self.logger.info(f"GM Action: DIALOGUE. Event: {gm_plan.event_title}")
                    if not gm_plan.dialogue_context:
                        self.logger.warning("Dialogue action chosen, but no dialogue_context was provided.")
                        event_text_for_log = f"({gm_plan.event_summary})" # Fallback
                    else:
                        # --- Step 3B: Loop Through and Call Character Agents ---
                        full_event_text = []
                        
                        # Initialize the authoritative state from the GM's plan. This will be updated by each actor.
                        assert gm_plan.state_update is not None, "GMActionPlan.state_update required for DIALOGUE"
                        assert gm_plan.dialogue_context is not None, "GMActionPlan.dialogue_context required for DIALOGUE"
                        latest_location = gm_plan.state_update.location
                        latest_date = gm_plan.state_update.date
                        latest_time = gm_plan.state_update.time

                        for dialogue_ctx in gm_plan.dialogue_context:
                            speaker_name = dialogue_ctx.speaker_name
                            speaking_character = None
    
                            # 1) Try to match by mention (e.g. <@12345>) -> match by character.user_id
                            mention_match = re.search(r"<@!?(\\d+)>", speaker_name or "")
                            if mention_match:
                                try:
                                    mention_id = int(mention_match.group(1))
                                    speaking_character = next((c for c in characters if c.user_id == mention_id), None)
                                    if speaking_character:
                                        self.logger.info("Matched speaker by mention -> %s (user_id=%s)", speaking_character.name, mention_id)
                                except Exception as _e:
                                    self.logger.debug("Invalid mention id parsing for speaker_name=%s: %s", speaker_name, _e)
    
                            # 2) Exact name match
                            if not speaking_character:
                                speaking_character = next((c for c in characters if c.name == speaker_name), None)
    
                            # 3) Case-insensitive or fuzzy-ish contains match
                            if not speaking_character and speaker_name:
                                lower = speaker_name.lower()
                                speaking_character = next((c for c in characters if lower in (c.name or "").lower()), None)
    
                            # 4) Fallback to a random active character (per user's preference)
                            if not speaking_character:
                                self.logger.warning("Character '%s' not found for dialogue. Substituting with a random character from the story.", speaker_name)
                                if characters:
                                    speaking_character = random.choice(characters)
                                    self.logger.info("Substituted with random character: '%s'", speaking_character.name)
                                else:
                                    self.logger.error("No available characters to substitute.")
                                    await self._send_story_response(
                                        channel=cast(discord.TextChannel, message.channel),
                                        character=None,
                                        story_instance=story_instance,
                                        content=f"({speaker_name} 想要說話，但現場沒有其他人可以代勞...)"
                                    )
                                    continue
    
                            # Fetch recent conversation history
                            history_messages = [msg async for msg in cast(discord.TextChannel, message.channel).history(limit=20)]
                            history_messages.reverse()
    
                            dialogue_history = []
                            if story_instance.summaries:
                                for summary in story_instance.summaries[-5:]:
                                    dialogue_history.append({"role": "user", "content": f"[Contextual Summary: {summary}]"})
    
                            for msg in history_messages:
                                content = msg.content
                                role = "user"
                                author = cast(discord.abc.User, msg.author)
                                # Deterministic: ensure author.id is present and use a concrete int for comparisons
                                assert getattr(author, "id", None) is not None, "message author id must not be None"
                                author_id = cast(int, author.id)
                                if author_id == bot_user_id and msg.embeds:
                                    content = msg.embeds[0].description or ""
                                    role = "assistant"
                                elif author_id != bot_user_id:
                                    role = "user"
                                if content.strip():
                                    dialogue_history.append({"role": role, "content": content})
    
                            # Pass the most up-to-date world state to the character prompt
                            char_system_prompt, char_user_prompt = await self.prompt_engine.build_character_prompt(
                                character=speaking_character,
                                gm_context=dialogue_ctx,
                                guild_id=guild_id,
                                location=latest_location,
                                date=latest_date,
                                time=latest_time
                            )
    
                            # Call character model via ModelManager + LangChain create_agent
                            story_character_model, fallback = ModelManager().get_model("story_character_model")
                            agent = create_agent(story_character_model, tools=[],
                                                 system_prompt=char_system_prompt, response_format=CharacterAction, middleware=[fallback])
    
                            # Call character agent (single try; deterministic handling)
                            try:
                                response = await agent.ainvoke(cast(Any, {"messages": dialogue_history + [HumanMessage(content=char_user_prompt)]}))
                                self.logger.debug("Character agent raw response (speaker=%s): %r", speaker_name, response)
                            except Exception as e:
                                self.logger.error("Character agent invocation failed for speaker=%s: %s", speaker_name, e, exc_info=True)
                                try:
                                    await func.report_error(e, f"story.character_agent_invoke_failed speaker={speaker_name}")
                                except Exception:
                                    self.logger.exception("func.report_error failed when reporting character_agent_invoke failure")
                                continue
    
                            character_action = None
                            try:
                                # Deterministic parsing: agent must return structured_response/output as dict or JSON string.
                                if isinstance(response, dict):
                                    payload = response.get("structured_response") or response.get("output") or response.get("result") or response
                                else:
                                    payload = response

                                if isinstance(payload, str):
                                    character_action = CharacterAction.model_validate_json(payload)
                                elif isinstance(payload, dict):
                                    character_action = CharacterAction.model_validate(payload)
                                elif hasattr(payload, "model_dump"):
                                    character_action = CharacterAction.model_validate(payload.model_dump())
                                elif hasattr(payload, "dict"):
                                    character_action = CharacterAction.model_validate(payload.dict())
                                else:
                                    raise Exception(f"Unsupported CharacterAction payload type: {type(payload)}")
                            except Exception as e:
                                self.logger.warning("Failed to parse character action for %s: %s", speaker_name, e)
                                try:
                                    await func.report_error(e, f"story.character_action_parse_failed speaker={speaker_name}")
                                except Exception:
                                    self.logger.exception("func.report_error failed when reporting character action parse failure")
    
                            if character_action:
                                await self._send_story_response(
                                    channel=cast(discord.TextChannel, message.channel),
                                    character=speaking_character,
                                    story_instance=story_instance,
                                    content=character_action,
                                )
                                event_text = f"{character_action.action or ''} {character_action.dialogue} {character_action.thought or ''}".strip()
                                full_event_text.append(f"{speaker_name}: {event_text}")
    
                                # The actor's action now becomes the new authoritative state for the next actor.
                                latest_location = character_action.location
                                latest_date = character_action.date
                                latest_time = character_action.time
                            else:
                                self.logger.warning("Failed to generate action for character '%s'.", speaker_name)

                        event_text_for_log = "\n".join(full_event_text) if full_event_text else f"({gm_plan.event_summary})"

                # --- Step 4: Update World State & Relationships ---
                # Use the final state, as determined by the last actor, to update the world.
                story_instance.current_location = latest_location
                story_instance.current_date = latest_date
                story_instance.current_time = latest_time
                self.logger.info(f"State updated by actor's final action: Loc={story_instance.current_location}, Date={story_instance.current_date}, Time={story_instance.current_time}")
                
                await self._update_relationships(db, story_instance.channel_id, gm_plan.relationships_update or [])
                
                updated_instance = story_instance
                
                # --- Step 5: Record Event ---
                await self._record_event(db, world, updated_instance, gm_plan, event_text_for_log)
                
                # --- Step 5.5: Handle Summary Generation ---
                updated_instance.message_counter += 1
                if updated_instance.message_counter >= 20:
                    self.logger.info(f"Message counter reached {updated_instance.message_counter}, generating summary for story {updated_instance.channel_id}")
                    await self._generate_and_save_summary(updated_instance)
                else:
                    db.save_story_instance(updated_instance)

            except (json.JSONDecodeError, ValidationError) as e:
                self.logger.error(f"Error in V5 story generation pipeline: {e}", exc_info=True)
                await message.reply("故事之神的大腦似乎纏在一起了，祂需要一點時間來解開... 請稍後再試。", allowed_mentions=_ALLOWED_MENTIONS)
            except Exception as e:
                self.logger.error(f"An unexpected error occurred in V5 story generation: {e}", exc_info=True)
                await message.reply("一陣無法預測的宇宙射線干擾了故事的進行，請稍後再試...", allowed_mentions=_ALLOWED_MENTIONS)

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
            assert isinstance(channel, discord.TextChannel), "channel must be a TextChannel for history access"
            history_messages = [msg async for msg in cast(discord.TextChannel, channel).history(limit=30)]
            history_messages.reverse()
            assert self.bot.user is not None, "bot.user must not be None"
            bot_user_id = cast(int, self.bot.user.id)

            # Format history into the required List[Dict[str, str]] format
            dialogue_history = []
            for msg in history_messages:
                content = msg.content
                role = "user"
                author = cast(discord.abc.User, msg.author)
                # Deterministic: ensure author.id is present and use a concrete int for comparisons
                assert getattr(author, "id", None) is not None, "message author id must not be None"
                author_id = cast(int, author.id)
                if author_id == bot_user_id and msg.embeds:
                    content = msg.embeds[0].description or ""
                    role = "assistant"
                elif author_id != bot_user_id:
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

            # Call summary model via ModelManager + LangChain create_agent
            story_summary_model, fallback = ModelManager().get_model("story_summary_model")
            agent = create_agent(story_summary_model, tools=[], system_prompt=summary_system_prompt, middleware=[fallback])
            response = await agent.ainvoke(cast(Any, {"messages": [HumanMessage(content=summary_inst), dialogue_history]}))
            summary_text = ""
            if isinstance(response, dict) and ("structured_response" in response or "output" in response):
                summary_text = str(response.get("structured_response") or response.get("output")).strip()
            else:
                summary_text = str(response).strip()

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

        outline_inst = HumanMessage("Based on the following 10 plot summaries, please synthesize them into a single, high-level outline paragraph.")

        # Format summaries into the dialogue history structure
        dialogue_history = HumanMessage(f"## Recent Plot Summaries\n{formatted_summaries}")

        try:
            # Call outline model via ModelManager + LangChain create_agent
            story_outline_model, fallback = ModelManager().get_model("story_outline_model")
            agent = create_agent(story_outline_model, tools=[], system_prompt=outline_system_prompt, middleware=[fallback])
            response = await agent.ainvoke(cast(Any, {"messages": [outline_inst, dialogue_history]}))
            outline_text = ""
            if isinstance(response, dict) and ("structured_response" in response or "output" in response):
                outline_text = str(response.get("structured_response") or response.get("output")).strip()
            else:
                outline_text = str(response).strip()

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
        assert interaction.guild_id is not None, "interaction.guild_id must not be None"
        assert interaction.channel_id is not None, "interaction.channel_id must not be None"
        db = self._get_db(cast(int, interaction.guild_id))
        world = db.get_world(world_name)
        if not world:
            self.logger.error(f"FATAL: Could not find world '{world_name}' during story start.")
            await interaction.edit_original_response(content="❌ 無法載入世界資料，故事無法開始。", embed=None, view=None, allowed_mentions=_ALLOWED_MENTIONS)
            return

        if use_narrator:
            # This is the standard path with a narrator
            self.logger.info(f"Starting story '{world_name}' with narrator.")
            story_instance = StoryInstance(
                channel_id=cast(int, interaction.channel_id),
                guild_id=cast(int, interaction.guild_id),
                world_name=world_name,
                current_date=initial_date,
                current_time=initial_time,
                current_location=initial_location,
                active_character_ids=character_ids,
                is_active=True,
                narration_enabled=True,
                message_counter=0,
                summaries=[],
                outlines=[]
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
                await interaction.edit_original_response(content="❌ 錯誤：選擇的角色無法載入，故事無法開始。", embed=None, view=None, allowed_mentions=_ALLOWED_MENTIONS)
                return

            director_character = all_selected_chars[0]
            self.logger.info(f"Designated director: {director_character.name} (ID: {director_character.character_id})")

            actor_characters = all_selected_chars[1:]
            self.logger.info(f"Designated {len(actor_characters)} actors.")

            self.logger.info("Preparing to create StoryInstance...")
            story_instance = StoryInstance(
                channel_id=cast(int, interaction.channel_id),
                guild_id=cast(int, interaction.guild_id),
                world_name=world_name,
                current_date=initial_date,
                current_time=initial_time,
                current_location=initial_location,
                active_character_ids=character_ids,
                is_active=True,
                narration_enabled=True,
                message_counter=0,
                summaries=[],
                outlines=[]
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
        assert interaction.guild is not None, "interaction.guild must not be None"
        db = self._get_db(cast(int, interaction.guild.id))
        world = db.get_world(story_instance.world_name)
        assert world is not None, "world must be found for story start"

        async with cast(discord.TextChannel, interaction.channel).typing():
            try:
                # --- Step 1: Build the prompt for the GM to start the story ---
                characters = self.character_db.get_characters_by_ids(story_instance.active_character_ids)
                gm_prompt = await self.prompt_engine.build_story_start_prompt(story_instance, world, characters)
                
                # --- Step 2: Call GM Model for a structured plan ---
                # Call GM model for initial scene via ModelManager + LangChain create_agent
                story_gm_model, fallback = ModelManager().get_model("story_gm_model")
                agent = create_agent(story_gm_model, tools=[], system_prompt=gm_prompt, response_format=GMActionPlan, middleware=[fallback])
                message_list = [HumanMessage("You are a helpful storytelling assistant. Your output MUST be a single, valid JSON object that conforms to the requested schema.")]
                response = await agent.ainvoke(cast(Any, {"messages": message_list}))

                gm_plan = None
                try:
                    resp_payload = None
                    if isinstance(response, dict):
                        resp_payload = response.get("structured_response") or response.get("output") or response.get("result") or response
                    else:
                        resp_payload = response

                    if isinstance(resp_payload, str):
                        gm_plan = GMActionPlan.model_validate_json(resp_payload)
                    elif isinstance(resp_payload, dict):
                        gm_plan = GMActionPlan.model_validate(resp_payload)
                    elif hasattr(resp_payload, "model_dump"):
                        gm_plan = GMActionPlan.model_validate(resp_payload.model_dump())
                    elif hasattr(resp_payload, "dict"):
                        gm_plan = GMActionPlan.model_validate(resp_payload.dict())
                    else:
                        raise Exception(f"Unsupported GMActionPlan payload type: {type(resp_payload)}")
                except Exception as e:
                    self.logger.error("Failed to parse GMActionPlan from agent response (first scene): %s", e)
                    try:
                        await func.report_error(e, "story.gm_action_parse_failed_first_scene")
                    except Exception:
                        self.logger.exception("func.report_error failed when reporting gm_action_parse_failed_first_scene")
                    raise

                # --- Step 3: Update World State & Relationships (if any) ---
                updated_instance = await self.state_manager.update_state_from_gm_plan(story_instance, gm_plan)
                await self._update_relationships(db, updated_instance.channel_id, gm_plan.relationships_update or [])
 
                # --- Step 4: Record the opening event ---
                await self._record_event(db, world, updated_instance, gm_plan, gm_plan.narration_content or "")
                
                # Save the final state of the instance
                db.save_story_instance(updated_instance)
 
                # --- Step 5: Send the opening narration to the channel ---
                await self._send_story_response(
                    channel=cast(discord.TextChannel, interaction.channel),
                    character=None,  # Narrator speaks first
                    story_instance=updated_instance,
                    content=gm_plan.narration_content or "",
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
                
                await interaction.edit_original_response(content=None, embed=embed, view=None, allowed_mentions=_ALLOWED_MENTIONS)
                self.logger.info(f"V5 story started successfully in channel {interaction.channel_id}")
                
            except Exception as e:
                self.logger.error(f"An unexpected error occurred in V5 first scene generation: {e}", exc_info=True)
                await interaction.edit_original_response(content="一陣無法預測的宇宙射線干擾了故事的進行，請稍後再試...", embed=None, view=None, allowed_mentions=_ALLOWED_MENTIONS)