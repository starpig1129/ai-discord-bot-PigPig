import discord
from discord.ext import commands
import logging
import random
from typing import Dict, List, Optional, Any, cast, TypeVar, Type
import aiohttp
from pydantic import BaseModel
from function import func

from llm.model_manager import ModelManager
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from .database import StoryDB, CharacterDB
from .models import (
    StoryInstance, StoryWorld, StoryCharacter, PlayerRelationship, 
    Event, Location, GMActionPlan, RelationshipUpdate, CharacterAction,
    StorySummary, StoryOutline
)
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

T = TypeVar('T', bound=BaseModel)


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

    def _extract_structured_response(
        self, 
        response: Any, 
        expected_model: Type[T], 
        context: str
    ) -> Optional[T]:
        """
        Unified extractor for structured agent responses.

        Args:
            response: Raw response returned by agent.ainvoke()
            expected_model: Expected Pydantic model class
            context: Logging context (e.g., "GM Agent", "Character Agent")

        Returns:
            Parsed model instance on success, None on failure.
        """
        try:
            # Step 1: 從響應中提取 payload
            payload = None
            if isinstance(response, dict):
                # 優先順序: structured_response > output > result > 整個 response
                payload = (
                    response.get("structured_response") or 
                    response.get("output") or 
                    response.get("result") or 
                    response
                )
            else:
                payload = response
            
            # Step 2: 檢查 payload 是否已經是目標類型
            if isinstance(payload, expected_model):
                self.logger.debug(f"{context}: Payload already correct type")
                return payload
            
            # Step 3: 根據 payload 類型進行轉換
            if isinstance(payload, str):
                # JSON 字符串
                result = expected_model.model_validate_json(payload)
                self.logger.debug(f"{context}: Parsed from JSON string")
                return result
            elif isinstance(payload, dict):
                # 字典
                result = expected_model.model_validate(payload)
                self.logger.debug(f"{context}: Parsed from dict")
                return result
            elif hasattr(payload, "model_dump"):
                # Pydantic v2 模型
                result = expected_model.model_validate(payload.model_dump())
                self.logger.debug(f"{context}: Parsed from Pydantic v2 model")
                return result
            elif hasattr(payload, "dict"):
                # Pydantic v1 模型
                result = expected_model.model_validate(payload.dict())
                self.logger.debug(f"{context}: Parsed from Pydantic v1 model")
                return result
            else:
                raise ValueError(f"Unsupported payload type: {type(payload)}")
                
        except Exception as e:
            self.logger.error(
                f"{context}: Failed to extract {expected_model.__name__}: {e}",
                exc_info=True
            )
            try:
                import asyncio
                asyncio.create_task(func.report_error(
                    e,
                    f"story.extract_structured_response_failed "
                    f"context={context} model={expected_model.__name__}"
                ))
            except Exception:
                self.logger.exception("func.report_error failed")
            return None

    # ========================================================================
    # 初始化與干預
    # ========================================================================

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
        assert interaction.guild_id is not None, "interaction.guild_id must not be None"
        assert interaction.channel_id is not None, "interaction.channel_id must not be None"
        db = self._get_db(cast(int, interaction.guild_id))
        story_instance = db.get_story_instance(cast(int, interaction.channel_id))
        if not story_instance or not story_instance.is_active:
            await interaction.response.send_message(
                self.language_manager.translate(str(interaction.guild_id), "story", "intervene", "no_active_story"),
                ephemeral=True,
                allowed_mentions=_ALLOWED_MENTIONS
            )
            return
            
        modal = InterventionModal(self)
        await interaction.response.send_modal(modal)

    # ========================================================================
    # 關係與事件更新
    # ========================================================================

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
                # Find user by display name
                user = discord.utils.find(lambda u: u.display_name == update.user_name, self.bot.users)
                if not user:
                    self.logger.warning(f"Could not find user by display name: {update.user_name}")
                    continue

                # Find character by name from the pre-fetched list
                char = next((c for c in all_characters_in_guild if c.name == update.character_name), None)
                if not char:
                    self.logger.warning(f"Could not find character by name: {update.character_name}")
                    continue

                # Find relationship from the pre-fetched list
                relationship = next(
                    (r for r in all_relationships_in_story 
                     if r.user_id == user.id and r.character_id == char.character_id), 
                    None
                )
                
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
                self.logger.error(
                    f"Failed to update relationship for {update.character_name}: {e}", 
                    exc_info=True
                )

    async def _record_event(
        self, 
        db: StoryDB, 
        world: StoryWorld, 
        instance: StoryInstance, 
        gm_plan: GMActionPlan, 
        final_content: str
    ):
        """Creates and records an event in the world state."""
        current_location_obj = next(
            (loc for loc in world.locations if loc.name == instance.current_location), 
            None
        )
        
        if not current_location_obj:
            self.logger.warning(
                f"Location '{instance.current_location}' not found in world "
                f"'{world.world_name}' for event recording."
            )
            # As a fallback, create the location if it doesn't exist
            current_location_obj = Location(name=instance.current_location)
            world.locations.append(current_location_obj)

        # The event's timestamp should reflect the in-story time, not real-world time
        event_timestamp = f"{instance.current_date} {instance.current_time}"

        event = Event(
            title=gm_plan.event_title,
            summary=gm_plan.event_summary,
            full_content=final_content,
            timestamp=event_timestamp
        )
        current_location_obj.events.append(event)
        
        db.save_world(world)
        self.logger.info(
            f"Recorded event '{event.title}' in "
            f"'{world.world_name}/{instance.current_location}'."
        )

    # ========================================================================
    # 消息發送
    # ========================================================================

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
            embed.add_field(
                name="📍 地點", 
                value=story_instance.current_location or "未知", 
                inline=True
            )
            embed.add_field(
                name="📅 日期", 
                value=story_instance.current_date or "未知", 
                inline=True
            )
            embed.add_field(
                name="⏰ 時間", 
                value=story_instance.current_time or "未知", 
                inline=True
            )

        # Fetch and add player relationships
        relationships = db.get_relationships_for_story(story_instance.channel_id)
        relationships = db.get_relationships_for_story(story_instance.channel_id)
        if relationships:
            relationship_lines = []
            for rel in relationships:
                char = self.character_db.get_character(rel.character_id)
                try:
                    user = await self.bot.fetch_user(rel.user_id)
                    user_name = user.display_name
                except discord.NotFound:
                    user_name = self.language_manager.translate("0", "system", "user", "id_format", id=rel.user_id)

                if char:
                    relationship_lines.append(
                        f"**{user_name}** {self.language_manager.translate('0', 'story', 'labels', 'with')} **{char.name}**: {rel.description}"
                    )

            if relationship_lines:
                embed.add_field(
                    name=self.language_manager.translate("0", "story", "labels", "relationships"),
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
                self.logger.error(
                    f"Webhook send failed for character {character.name}: {e}. "
                    f"Falling back to channel.send."
                )
                await channel.send(embed=embed, allowed_mentions=_ALLOWED_MENTIONS)
        else:
            await channel.send(embed=embed, allowed_mentions=_ALLOWED_MENTIONS)

    # ========================================================================
    # 核心故事處理邏輯
    # ========================================================================

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
            await message.reply(
                self.language_manager.translate(str(guild_id), "story", "errors", "world_not_found", world_name=story_instance.world_name),
                allowed_mentions=_ALLOWED_MENTIONS
            )
            return

        characters = [
            char for char_id in story_instance.active_character_ids 
            if (char := self.character_db.get_character(char_id))
        ]
        self.logger.info(
            f"V5 Orchestrator: Processing message in c:{channel_id} w:{world.world_name}"
        )

        async with cast(discord.TextChannel, message.channel).typing():
            try:
                # --- Step 1: Call GM Agent for a structured plan ---
                intervention_text = self.interventions.pop(channel_id, None)
                if intervention_text:
                    self.logger.info(
                        f"Applying intervention for channel {channel_id}: {intervention_text}"
                    )

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

                # Prepare dialogue history for the GM
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

                # Call GM agent
                story_gm_model, fallback = ModelManager().get_model("story_gm_model")
                agent = create_agent(
                    story_gm_model, 
                    tools=[], 
                    system_prompt=gm_prompt, 
                    response_format=GMActionPlan,
                    middleware=[fallback]
                )
                message_list = [HumanMessage(content=message.content)] + gm_dialogue_history
                response = await agent.ainvoke(cast(Any, {"messages": message_list}))

                # 使用統一方法提取結構化響應
                gm_plan = self._extract_structured_response(response, GMActionPlan, "GM Agent")
                if not gm_plan:
                    await message.reply(
                        self.language_manager.translate(str(guild_id), "story", "errors", "gm_plan_failed"),
                        allowed_mentions=_ALLOWED_MENTIONS
                    )
                    return

                # --- Step 3: Execute the plan (NARRATE or DIALOGUE) ---
                event_text_for_log = ""
                latest_location = story_instance.current_location
                latest_date = story_instance.current_date
                latest_time = story_instance.current_time

                if gm_plan.action_type == "NARRATE":
                    self.logger.info(f"GM Action: NARRATE. Event: {gm_plan.event_title}")
                    if gm_plan.narration_content:
                        await self._send_story_response(
                            channel=cast(discord.TextChannel, message.channel),
                            character=None,
                            story_instance=story_instance,
                            content=gm_plan.narration_content,
                        )
                        event_text_for_log = gm_plan.narration_content
                    else:
                        self.logger.info("Narration is disabled or was not generated.")
                        event_text_for_log = f"({gm_plan.event_summary})"
                
                elif gm_plan.action_type == "DIALOGUE":
                    self.logger.info(f"GM Action: DIALOGUE. Event: {gm_plan.event_title}")
                    if not gm_plan.dialogue_context:
                        self.logger.warning(
                            "Dialogue action chosen, but no dialogue_context was provided."
                        )
                        event_text_for_log = f"({gm_plan.event_summary})"
                    else:
                        # --- Step 3B: Loop Through and Call Character Agents ---
                        full_event_text = []
                        
                        assert gm_plan.state_update is not None,                             "GMActionPlan.state_update required for DIALOGUE"
                        assert gm_plan.dialogue_context is not None,                             "GMActionPlan.dialogue_context required for DIALOGUE"
                        
                        latest_location = gm_plan.state_update.location
                        latest_date = gm_plan.state_update.date
                        latest_time = gm_plan.state_update.time

                        for dialogue_ctx in gm_plan.dialogue_context:
                            speaker_name = dialogue_ctx.speaker_name
                            speaking_character = await self._find_speaking_character(
                                speaker_name, 
                                characters, 
                                message.channel
                            )
                            
                            if not speaking_character:
                                continue

                            # Fetch recent conversation history
                            history_messages = [
                                msg async for msg 
                                in cast(discord.TextChannel, message.channel).history(limit=20)
                            ]
                            history_messages.reverse()

                            dialogue_history = []
                            if story_instance.summaries:
                                for summary in story_instance.summaries[-5:]:
                                    dialogue_history.append({
                                        "role": "user", 
                                        "content": f"[Contextual Summary: {summary}]"
                                    })

                            for msg in history_messages:
                                content = msg.content
                                role = "user"
                                author = cast(discord.abc.User, msg.author)
                                assert getattr(author, "id", None) is not None,                                     "message author id must not be None"
                                author_id = cast(int, author.id)
                                
                                if author_id == bot_user_id and msg.embeds:
                                    content = msg.embeds[0].description or ""
                                    role = "assistant"
                                elif author_id != bot_user_id:
                                    role = "user"
                                
                                if content.strip():
                                    dialogue_history.append({"role": role, "content": content})

                            # Build character prompt
                            char_system_prompt, char_user_prompt =                                 await self.prompt_engine.build_character_prompt(
                                    character=speaking_character,
                                    gm_context=dialogue_ctx,
                                    guild_id=guild_id,
                                    location=latest_location,
                                    date=latest_date,
                                    time=latest_time
                                )

                            # Call character agent
                            story_character_model, fallback =                                 ModelManager().get_model("story_character_model")
                            agent = create_agent(
                                story_character_model, 
                                tools=[],
                                system_prompt=char_system_prompt, 
                                response_format=CharacterAction, 
                                middleware=[fallback]
                            )

                            try:
                                response = await agent.ainvoke(cast(Any, {
                                    "messages": dialogue_history + [
                                        HumanMessage(content=char_user_prompt)
                                    ]
                                }))
                            except Exception as e:
                                self.logger.error(
                                    f"Character agent invocation failed for "
                                    f"speaker={speaker_name}: {e}", 
                                    exc_info=True
                                )
                                try:
                                    import asyncio
                                    asyncio.create_task(func.report_error(
                                        e,
                                        f"story.character_agent_invoke_failed "
                                        f"speaker={speaker_name}"
                                    ))
                                except Exception:
                                    self.logger.exception(
                                        "func.report_error failed when reporting "
                                        "character_agent_invoke failure"
                                    )
                                continue

                            # 使用統一方法提取結構化響應
                            character_action = self._extract_structured_response(
                                response,
                                CharacterAction,
                                f"Character Agent ({speaker_name})"
                            )

                            if character_action:
                                await self._send_story_response(
                                    channel=cast(discord.TextChannel, message.channel),
                                    character=speaking_character,
                                    story_instance=story_instance,
                                    content=character_action,
                                )
                                event_text = (
                                    f"{character_action.action or ''} "
                                    f"{character_action.dialogue} "
                                    f"{character_action.thought or ''}"
                                ).strip()
                                full_event_text.append(f"{speaker_name}: {event_text}")

                                # Update state from character action
                                latest_location = character_action.location
                                latest_date = character_action.date
                                latest_time = character_action.time
                            else:
                                self.logger.warning(
                                    f"Failed to generate action for character '{speaker_name}'."
                                )

                        event_text_for_log = (
                            "\n".join(full_event_text) 
                            if full_event_text 
                            else f"({gm_plan.event_summary})"
                        )

                # --- Step 4: Update World State & Relationships ---
                story_instance.current_location = latest_location
                story_instance.current_date = latest_date
                story_instance.current_time = latest_time
                self.logger.info(
                    f"State updated: Loc={story_instance.current_location}, "
                    f"Date={story_instance.current_date}, Time={story_instance.current_time}"
                )
                
                await self._update_relationships(
                    db, 
                    story_instance.channel_id, 
                    gm_plan.relationships_update or []
                )
                
                updated_instance = story_instance
                
                # --- Step 5: Record Event ---
                await self._record_event(
                    db, 
                    world, 
                    updated_instance, 
                    gm_plan, 
                    event_text_for_log
                )
                
                # --- Step 5.5: Handle Summary Generation ---
                updated_instance.message_counter += 1
                if updated_instance.message_counter >= 20:
                    self.logger.info(
                        f"Message counter reached {updated_instance.message_counter}, "
                        f"generating summary for story {updated_instance.channel_id}"
                    )
                    await self._generate_and_save_summary(updated_instance)
                else:
                    db.save_story_instance(updated_instance)

            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred in V5 story generation: {e}",
                    exc_info=True
                )
                try:
                    import asyncio
                    asyncio.create_task(func.report_error(e, "story.v5_unexpected_error"))
                except Exception:
                    self.logger.exception("func.report_error failed")
                await message.reply(
                    self.language_manager.translate(str(guild_id), "system", "errors", "unexpected"),
                    allowed_mentions=_ALLOWED_MENTIONS
                )

    async def _find_speaking_character(
        self, 
        speaker_name: Optional[str], 
        characters: List[StoryCharacter],
        channel: discord.abc.Messageable
    ) -> Optional[StoryCharacter]:
        """
        統一的角色查找邏輯，支持多種匹配方式。
        """
        import re
        
        speaking_character = None

        # 1) Try to match by mention (e.g. <@12345>)
        if speaker_name:
            mention_match = re.search(r"<@!?(\d+)>", speaker_name)
            if mention_match:
                try:
                    mention_id = int(mention_match.group(1))
                    speaking_character = next(
                        (c for c in characters if c.user_id == mention_id), 
                        None
                    )
                    if speaking_character:
                        self.logger.info(
                            f"Matched speaker by mention -> {speaking_character.name} "
                            f"(user_id={mention_id})"
                        )
                except Exception as e:
                    self.logger.debug(
                        f"Invalid mention id parsing for speaker_name={speaker_name}: {e}"
                    )

        # 2) Exact name match
        if not speaking_character and speaker_name:
            speaking_character = next(
                (c for c in characters if c.name == speaker_name), 
                None
            )

        # 3) Case-insensitive contains match
        if not speaking_character and speaker_name:
            lower = speaker_name.lower()
            speaking_character = next(
                (c for c in characters if lower in (c.name or "").lower()), 
                None
            )

        # 4) Fallback to random character
        if not speaking_character:
            self.logger.warning(
                f"Character '{speaker_name}' not found for dialogue. "
                f"Substituting with a random character."
            )
            if characters:
                speaking_character = random.choice(characters)
                self.logger.info(f"Substituted with random character: '{speaking_character.name}'")
            else:
                self.logger.error("No available characters to substitute.")
                await self._send_story_response(
                    channel=cast(discord.TextChannel, channel),
                    character=None,
                    story_instance=None,  # type: ignore
                    content=self.language_manager.translate("0", "story", "dialogue", "no_substitute", speaker=speaker_name)
                )
                return None

        return speaking_character

    # ========================================================================
    # 摘要與大綱生成（使用結構化輸出）
    # ========================================================================

    async def _generate_and_save_summary(self, story_instance: StoryInstance):
        """
        Generates a summary of the last 20-40 messages and saves it.
        Uses structured output (StorySummary).
        """
        db = self._get_db(story_instance.guild_id)
        channel = self.bot.get_channel(story_instance.channel_id)
        if not channel:
            self.logger.error(
                f"Cannot generate summary, channel {story_instance.channel_id} not found."
            )
            return

        self.logger.info(f"Generating summary for story in channel {channel.id}")
        try:
            # Fetch last 30 messages for context
            assert isinstance(channel, discord.TextChannel),                 "channel must be a TextChannel for history access"
            history_messages = [
                msg async for msg 
                in cast(discord.TextChannel, channel).history(limit=30)
            ]
            history_messages.reverse()
            assert self.bot.user is not None, "bot.user must not be None"
            bot_user_id = cast(int, self.bot.user.id)

            # Format history
            dialogue_history = []
            for msg in history_messages:
                content = msg.content
                role = "user"
                author = cast(discord.abc.User, msg.author)
                assert getattr(author, "id", None) is not None,                     "message author id must not be None"
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
                "Based on the provided conversation log, please provide a concise summary "
                "with key events and character developments. "
                "The summary should capture the essence of what happened. "
                "Output must be in JSON format matching the StorySummary schema."
            )
            
            summary_inst = (
                "Please provide a structured summary of the preceding conversation, "
                "including a one-paragraph summary, key events, and character developments."
            )

            # Call summary model with structured output
            story_summary_model, fallback = ModelManager().get_model("story_summary_model")
            agent = create_agent(
                story_summary_model, 
                tools=[], 
                system_prompt=summary_system_prompt,
                response_format=StorySummary,  # 使用結構化輸出
                middleware=[fallback]
            )
            response = await agent.ainvoke(cast(Any, {
                "messages": [HumanMessage(content=summary_inst)] + dialogue_history
            }))

            # 使用統一方法提取結構化響應
            summary_result = self._extract_structured_response(
                response,
                StorySummary,
                "Summary Agent"
            )

            if summary_result and summary_result.summary:
                story_instance.summaries.append(summary_result.summary)
                self.logger.info(
                    f"Generated summary for story {story_instance.channel_id}. "
                    f"Key events: {len(summary_result.key_events)}, "
                    f"Total summaries: {len(story_instance.summaries)}"
                )
                
                # Check if it's time to generate an outline
                if len(story_instance.summaries) > 0 and len(story_instance.summaries) % 10 == 0:
                    self.logger.info(
                        f"Summary count is a multiple of 10. "
                        f"Generating outline for story {story_instance.channel_id}."
                    )
                    await self._generate_and_save_outline(story_instance)
            else:
                self.logger.warning(
                    f"Summary generation resulted in empty text for "
                    f"story {story_instance.channel_id}."
                )

        except Exception as e:
            self.logger.error(
                f"Failed to generate summary for story {story_instance.channel_id}: {e}", 
                exc_info=True
            )
        finally:
            story_instance.message_counter = 0
            db.save_story_instance(story_instance)

    async def _generate_and_save_outline(self, story_instance: StoryInstance):
        """
        Generates a high-level outline from the last 10 summaries and saves it.
        Uses structured output (StoryOutline).
        """
        self.logger.info(f"Attempting to generate outline for story {story_instance.channel_id}.")

        if len(story_instance.summaries) < 10:
            self.logger.warning(
                f"Not enough summaries to generate an outline for "
                f"story {story_instance.channel_id}. "
                f"Need 10, have {len(story_instance.summaries)}."
            )
            return

        # Get the most recent 10 summaries
        recent_summaries = story_instance.summaries[-10:]
        formatted_summaries = "\n".join([f"{i+1}. {s}" for i, s in enumerate(recent_summaries)])

        outline_system_prompt = (
            "You are a master storyteller and editor. "
            "Based on the provided plot summaries, synthesize them into a high-level outline. "
            "Include major plot points and character arcs. "
            "Output must be in JSON format matching the StoryOutline schema."
        )

        outline_inst = HumanMessage(
            "Based on the following 10 plot summaries, synthesize them into a "
            "structured outline with major plot points and character arcs."
        )

        dialogue_history = HumanMessage(f"## Recent Plot Summaries\n{formatted_summaries}")

        try:
            # Call outline model with structured output
            story_outline_model, fallback = ModelManager().get_model("story_outline_model")
            agent = create_agent(
                story_outline_model, 
                tools=[], 
                system_prompt=outline_system_prompt,
                response_format=StoryOutline,  # 使用結構化輸出
                middleware=[fallback]
            )
            response = await agent.ainvoke(cast(Any, {
                "messages": [outline_inst, dialogue_history]
            }))

            # 使用統一方法提取結構化響應
            outline_result = self._extract_structured_response(
                response,
                StoryOutline,
                "Outline Agent"
            )

            if outline_result and outline_result.outline:
                story_instance.outlines.append(outline_result.outline)
                self.logger.info(
                    f"Generated outline for story {story_instance.channel_id}. "
                    f"Plot points: {len(outline_result.major_plot_points)}, "
                    f"Total outlines: {len(story_instance.outlines)}"
                )
            else:
                self.logger.warning(
                    f"Outline generation resulted in empty text for "
                    f"story {story_instance.channel_id}."
                )

        except Exception as e:
            self.logger.error(
                f"Failed to generate outline for story {story_instance.channel_id}: {e}", 
                exc_info=True
            )

    # ========================================================================
    # 故事啟動
    # ========================================================================

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
            await interaction.edit_original_response(
                content=self.language_manager.translate(str(interaction.guild_id), "story", "errors", "world_load_failed", world_name=world_name),
                embed=None,
                view=None,
                allowed_mentions=_ALLOWED_MENTIONS
            )
            return

        if use_narrator:
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
            db.save_story_instance(story_instance)
            await self.generate_first_scene(interaction, story_instance)

        else:
            self.logger.info("Entering 'use_narrator=False' logic branch.")
            
            self.logger.info(f"Received character_ids: {character_ids}")
            all_selected_chars = self.character_db.get_characters_by_ids(character_ids)
            self.logger.info(
                f"Fetched {len(all_selected_chars)} character objects from the database."
            )

            if not all_selected_chars:
                self.logger.error(
                    "Error: No character objects were fetched despite receiving IDs."
                )
                try:
                    await interaction.edit_original_response(
                        content=self.language_manager.translate(str(interaction.guild_id), "story", "errors", "characters_load_failed"),
                        embed=None,
                        view=None,
                        allowed_mentions=_ALLOWED_MENTIONS
                    )
                except Exception:
                    # Best-effort: ensure we report the error
                    pass
                return

            director_character = all_selected_chars[0]
            self.logger.info(
                f"Designated director: {director_character.name} "
                f"(ID: {director_character.character_id})"
            )

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
            db.save_story_instance(story_instance)
            self.logger.info(
                f"Successfully created story_instance for channel: {story_instance.channel_id}"
            )

            self.logger.info("Preparing to call self.generate_first_scene...")
            await self.generate_first_scene(interaction, story_instance)
            self.logger.info("Successfully completed call to generate_first_scene.")

    async def generate_first_scene(
        self, 
        interaction: discord.Interaction, 
        story_instance: StoryInstance
    ):
        """
        Generates the introductory scene for a new story using the v5 architecture.
        """
        self.logger.info(
            f"V5: Generating first scene for story in channel {interaction.channel_id}"
        )
        assert interaction.guild is not None, "interaction.guild must not be None"
        db = self._get_db(cast(int, interaction.guild.id))
        world = db.get_world(story_instance.world_name)
        assert world is not None, "world must be found for story start"

        async with cast(discord.TextChannel, interaction.channel).typing():
            try:
                # Build the prompt for the GM to start the story
                characters = self.character_db.get_characters_by_ids(
                    story_instance.active_character_ids
                )
                gm_prompt = await self.prompt_engine.build_story_start_prompt(
                    story_instance, 
                    world, 
                    characters
                )
                
                # Call GM Model for initial scene
                story_gm_model, fallback = ModelManager().get_model("story_gm_model")
                agent = create_agent(
                    story_gm_model, 
                    tools=[], 
                    system_prompt=gm_prompt, 
                    response_format=GMActionPlan, 
                    middleware=[fallback]
                )
                message_list = [HumanMessage(
                    "You are a helpful storytelling assistant. "
                    "Your output MUST be a single, valid JSON object that conforms "
                    "to the requested schema."
                )]
                response = await agent.ainvoke(cast(Any, {"messages": message_list}))

                # 使用統一方法提取結構化響應
                gm_plan = self._extract_structured_response(
                    response, 
                    GMActionPlan, 
                    "GM Agent (First Scene)"
                )
                
                if not gm_plan:
                    await interaction.edit_original_response(
                        content=self.language_manager.translate(str(interaction.guild_id), "story", "errors", "first_scene_failed"),
                        embed=None,
                        view=None,
                        allowed_mentions=_ALLOWED_MENTIONS
                    )
                    return

                # Update World State & Relationships
                updated_instance = await self.state_manager.update_state_from_gm_plan(
                    story_instance, 
                    gm_plan
                )
                await self._update_relationships(
                    db, 
                    updated_instance.channel_id, 
                    gm_plan.relationships_update or []
                )
 
                # Record the opening event
                await self._record_event(
                    db, 
                    world, 
                    updated_instance, 
                    gm_plan, 
                    gm_plan.narration_content or ""
                )
                
                # Save the final state
                db.save_story_instance(updated_instance)
 
                # Send the opening narration
                await self._send_story_response(
                    channel=cast(discord.TextChannel, interaction.channel),
                    character=None,
                    story_instance=updated_instance,
                    content=gm_plan.narration_content or "",
                )

                # Finalize the public "Story Started" message
                title = self.language_manager.translate(str(interaction.guild_id), "story", "start_scene", "title")
                description = self.language_manager.translate(str(interaction.guild_id), "story", "start_scene", "description", world_name=world.world_name)
                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=discord.Color.gold()
                )
                world_background = world.attributes.get('background', self.language_manager.translate(str(interaction.guild_id), "story", "start_scene", "no_background"))
                embed.add_field(
                    name=self.language_manager.translate(str(interaction.guild_id), "story", "start_scene", "world_background"),
                    value=world_background[:800] + ("..." if len(world_background) > 800 else ""),
                    inline=False
                )
                embed.add_field(name=self.language_manager.translate(str(interaction.guild_id), "story", "labels", "date"), value=updated_instance.current_date, inline=True)
                embed.add_field(name=self.language_manager.translate(str(interaction.guild_id), "story", "labels", "time"), value=updated_instance.current_time, inline=True)
                embed.add_field(
                    name=self.language_manager.translate(str(interaction.guild_id), "story", "labels", "location"),
                    value=updated_instance.current_location,
                    inline=False
                )
                
                characters = [
                    self.character_db.get_character(cid)
                    for cid in updated_instance.active_character_ids
                ]
                if characters:
                    selected_npcs = [char.name for char in characters if char]
                    embed.add_field(
                        name=self.language_manager.translate(str(interaction.guild_id), "story", "start_scene", "participants"),
                        value=", ".join(selected_npcs) if selected_npcs else self.language_manager.translate(str(interaction.guild_id), "story", "start_scene", "none"),
                        inline=False
                    )
    
                embed.set_footer(text=self.language_manager.translate(str(interaction.guild_id), "story", "start_scene", "footer"))
                
                await interaction.edit_original_response(
                    content=None,
                    embed=embed,
                    view=None,
                    allowed_mentions=_ALLOWED_MENTIONS
                )
                self.logger.info(
                    f"V5 story started successfully in channel {interaction.channel_id}"
                )
                
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred in V5 first scene generation: {e}",
                    exc_info=True
                )
                try:
                    import asyncio
                    asyncio.create_task(func.report_error(e, "story.first_scene_unexpected_error"))
                except Exception:
                    self.logger.exception("func.report_error failed")
                await interaction.edit_original_response(
                    content=self.language_manager.translate(str(interaction.guild_id), "system", "errors", "unexpected"),
                    embed=None,
                    view=None,
                    allowed_mentions=_ALLOWED_MENTIONS
                )