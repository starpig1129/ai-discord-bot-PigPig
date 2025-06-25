import discord
from discord.ext import commands
import logging
from typing import List

from .models import StoryInstance, StoryWorld, StoryCharacter
from cogs.memory.memory_manager import MemoryManager
from cogs.memory.search_engine import SearchQuery, SearchType
from cogs.system_prompt_manager import SystemPromptManagerCog

class StoryPromptEngine:
    """Builds high-quality prompts for the LLM to drive the story."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.memory_manager: MemoryManager = self.bot.memory_manager
        self.system_prompt_manager: SystemPromptManagerCog = self.bot.get_cog("SystemPromptManagerCog")

    async def build_story_prompt(
        self,
        instance: StoryInstance,
        world: StoryWorld,
        characters: List[StoryCharacter],
        user_input: str,
    ) -> str:
        """Constructs the full prompt for the LLM."""
        
        # 1. Get Base Personality (The "Narrator" personality)
        base_prompt = await self.system_prompt_manager.get_effective_system_prompt(
            str(instance.channel_id), str(instance.guild_id)
        )

        # 2. Search for relevant past events from MemoryManager
        relevant_events = await self._get_relevant_events(instance, user_input)

        # 3. Assemble the prompt
        prompt_parts = []
        prompt_parts.append(base_prompt)
        
        # --- Story Context Block ---
        prompt_parts.append("## Story Context")
        prompt_parts.append(f"### World: {world.world_name}")
        prompt_parts.append(f"**Background:** {world.background}")
        if world.rules:
            prompt_parts.append("**World Rules:**\n- " + "\n- ".join(world.rules))
        
        prompt_parts.append("### Current Situation")
        prompt_parts.append(f"**Location:** {instance.current_state.get('location', 'Unknown')}")
        prompt_parts.append(f"**Time:** {instance.current_state.get('time', 'Unknown')}")

        prompt_parts.append("### Characters Present")
        for char in characters:
            char_desc = f"- **{char.name}** ({'Player' if char.is_pc else 'NPC'}): {char.description}. Status: {char.status}."
            if char.inventory:
                char_desc += f" Inventory: {', '.join(char.inventory)}"
            prompt_parts.append(char_desc)

        if relevant_events:
            prompt_parts.append("### Recent Key Events (Memory)")
            prompt_parts.append("\n".join(relevant_events))

        if instance.event_log:
            prompt_parts.append("### Immediate Event Log (Last 5 events)")
            prompt_parts.append("\n".join([f"- {log}" for log in instance.event_log[-5:]]))

        # --- User Action Block ---
        prompt_parts.append("## User's Action")
        prompt_parts.append(f"The user, acting as their character or influencing the scene, says/does the following:")
        prompt_parts.append(f"> {user_input}")

        # --- GM Instructions Block ---
        prompt_parts.append("## Your Task as Game Master (GM)")
        prompt_parts.append(
            "You are the Game Master. Your task is to narrate the consequences of the user's action. "
            "Describe the outcome, how the world and other characters react, and what happens next. "
            "Keep the story moving forward. Be descriptive and engaging. "
            "Your response should ONLY be the story narration."
        )

        return "\n\n".join(prompt_parts)

    async def _get_relevant_events(self, instance: StoryInstance, user_input: str) -> List[str]:
        """Retrieves relevant past events using the MemoryManager."""
        if not self.memory_manager or not self.memory_manager.is_enabled:
            return []

        try:
            query_text = f"Location: {instance.current_state.get('location', '')}. User action: {user_input}"
            search_query = SearchQuery(
                query=query_text,
                channel_id=str(instance.channel_id),
                limit=5,
                search_type=SearchType.HYBRID
            )
            search_result = await self.memory_manager.search_memory(search_query)
            
            # We only want the content of the memory
            return [message.content for message in search_result.messages]
        except Exception as e:
            self.logger.error(f"Failed to search memory for story instance {instance.channel_id}: {e}")
            return []