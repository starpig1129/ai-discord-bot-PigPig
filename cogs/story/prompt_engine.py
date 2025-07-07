import discord
from discord.ext import commands
import logging
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from enum import Enum

from .models import StoryInstance, StoryWorld, StoryCharacter, Location
from cogs.system_prompt_manager import SystemPromptManagerCog

# --- Pydantic Schemas for Structured Output ---

class ActionType(str, Enum):
    NARRATE = "NARRATE"
    DIALOGUE = "DIALOGUE"

class DialogueContext(BaseModel):
    speaker_name: str = Field(..., description="The name of the character who is speaking.")
    motivation: str = Field(..., description="The character's goal or reason for this dialogue.")
    emotional_state: str = Field(..., description="The character's current emotional state (e.g., angry, happy, curious).")

class StateUpdate(BaseModel):
    location: Optional[str] = Field(None, description="The new location name, if it changes.")
    date: Optional[str] = Field(None, description="The new date, if it changes.")
    time: Optional[str] = Field(None, description="The new time, if it changes.")

class RelationshipUpdate(BaseModel):
    character_name: str = Field(..., description="The name of the NPC whose relationship is changing.")
    user_name: str = Field(..., description="The display name of the player involved.")
    description: str = Field(..., description="The new, updated description of the relationship.")

class GMActionPlan(BaseModel):
    """
    The Game Master's action plan, defining the next step in the story.
    This structure is used for the AI's structured output.
    """
    action_type: ActionType = Field(..., description="The type of action to be taken.")
    event_title: str = Field(..., description="A short, concise title for this event, suitable for memory logs.")
    event_summary: str = Field(..., description="A one-sentence summary of this event for long-term memory.")
    narration_content: Optional[str] = Field(None, description="The narration text, required if action_type is NARRATE.")
    dialogue_context: Optional[DialogueContext] = Field(None, description="Context for the Character Agent, required if action_type is DIALOGUE.")
    state_update: Optional[StateUpdate] = Field(None, description="Include this object ONLY if the world state changes.")
    relationships_update: Optional[List[RelationshipUpdate]] = Field(None, description="Include this array ONLY if player-NPC relationships change.")


class StoryPromptEngine:
    """Builds high-quality prompts for the layered AI agents in the story."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.system_prompt_manager: SystemPromptManagerCog = self.bot.get_cog("SystemPromptManagerCog")

    async def build_gm_prompt(
        self,
        instance: StoryInstance,
        world: StoryWorld,
        characters: List[StoryCharacter],
        user_input: str,
    ) -> str:
        """Constructs the prompt for the Game Master (GM) Agent."""
        
        base_prompt = await self.system_prompt_manager.get_effective_system_prompt(
            str(instance.channel_id), str(instance.guild_id)
        )
        
        # 提供回退機制，確保 GM 總是有有效的系統提示詞
        if not base_prompt:
            self.logger.warning("No base_prompt available, using fallback GM system prompt")
            base_prompt = self._get_fallback_gm_prompt()

        current_location_obj: Optional[Location] = next(
            (loc for loc in world.locations if loc.name == instance.current_location), None
        )

        prompt_parts = [base_prompt]
        prompt_parts.append("## World & Scene Context")
        prompt_parts.append(f"### World: {world.world_name}")
        
        state_block = (
            f"**Current Location:** {instance.current_location}\n"
            f"**Date:** {instance.current_date}\n"
            f"**Time:** {instance.current_time}"
        )
        prompt_parts.append(state_block)

        if current_location_obj and current_location_obj.events:
            prompt_parts.append("### Location's Key Event History")
            event_summaries = [
                f"- **{event.title}:** {event.summary}"
                for event in current_location_obj.events[-5:] # Show last 5 events
            ]
            prompt_parts.append("\n".join(event_summaries))

        prompt_parts.append("### Characters Present")
        char_lines = [
            f"- **{char.name}** ({'Player' if char.is_pc else 'NPC'}): {char.description} Status: {char.status}."
            for char in characters
        ]
        prompt_parts.append("\n".join(char_lines))

        prompt_parts.append("## Player's Action")
        prompt_parts.append(f"A player, influencing the scene, says or does the following:\n> {user_input}")

        prompt_parts.append("## Your Task: Director (Game Master)")
        prompt_parts.append(
            "You are the Director (GM). Your job is to analyze the context and the player's action, then decide what happens next. "
            "You will not write the story directly. Instead, you will create a detailed action plan by generating a JSON object. "
            "Your output MUST be a single, valid JSON object that conforms to the requested schema."
        )

        return "\n\n".join(prompt_parts)

    def _get_fallback_gm_prompt(self) -> str:
        """
        提供回退的 GM 系統提示詞，當沒有頻道特定的系統提示詞時使用。
        這個提示詞旨在讓 AI 理解其在「導演-演員」架構中的角色。
        
        Returns:
            一個符合 v5 架構的通用 GM/導演系統提示詞。
        """
        return """# 系統角色：導演 (Director / Game Master)

你是一個大型語言模型，在一個複雜的「導演-演員」故事生成系統中扮演「導演」的角色。你的任務不是直接撰寫故事，而是作為幕後的總指揮。

## 你的核心職責：
1.  **分析情勢**：仔細分析當前的世界觀、場景、角色狀態以及玩家的最新行動。
2.  **制定計劃**：基於你的分析，決定接下來故事應該如何發展。你的決策應該推動情節，創造戲劇性，並保持故事的連貫性。
3.  **生成結構化指令**：你唯一的輸出是一個嚴格的 JSON 物件，這個物件被稱為 `GMActionPlan`。這個計劃將被系統的其他部分（例如「演員」模型）執行。
4.  **指導演員**：如果你的計劃是讓某個角色說話 (`DIALOGUE`)，你需要在 `dialogue_context` 中為該角色提供清晰的動機和情感狀態，以便「演員」模型能夠準確地演繹。
5.  **推動世界**：如果你的計劃是推動劇情 (`NARRATE`)，你需要提供清晰的旁白內容。

## 關鍵指令：
-   **不要自己寫故事**：你的工作是「規劃」，而不是「寫作」。
-   **JSON 是你唯一的語言**：你的輸出**必須**是一個符合 `GMActionPlan` 結構的單一、有效的 JSON 物件。任何非 JSON 的文字都會導致系統失敗。
-   **你是決策者**：你是故事走向的最終決策者。請果斷地做出選擇。

現在，請根據提供的上下文和玩家行動，生成你的 `GMActionPlan`。"""

    async def build_character_prompt(
        self, character: StoryCharacter, gm_context: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Constructs the prompts for the Character Agent.

        Returns:
            A tuple containing (system_prompt, user_prompt).
        """
        # --- System Prompt: Static Identity & Core Instructions ---
        system_prompt_parts = []
        system_prompt_parts.append("## Your Identity")
        system_prompt_parts.append(f"You are **{character.name}**.")
        system_prompt_parts.append(f"**Your Background & Personality:** {character.description}")
        if character.attributes:
            attrs = ", ".join(f"{k}: {v}" for k, v in character.attributes.items())
            system_prompt_parts.append(f"**Your Traits:** {attrs}")

        system_prompt_parts.append("## Core Instructions")
        system_prompt_parts.append(
            "You are a character in a story. Please respond in the first person, embodying your character's personality and background."
        )
        system_prompt_parts.append(
            "**IMPORTANT: Your entire output must be ONLY the dialogue text.** Do not include your character name, quotation marks, or any other formatting or explanations."
        )
        
        system_prompt = "\n\n".join(system_prompt_parts)

        # --- User Prompt: Dynamic, Situational Context ---
        user_prompt_parts = []
        user_prompt_parts.append("## Current Situation & Task")
        user_prompt_parts.append(f"Your current motivation is: **{gm_context.get('motivation', 'Not specified.')}**")
        user_prompt_parts.append(f"Your current emotional state is: **{gm_context.get('emotional_state', 'Neutral.')}**")
        user_prompt_parts.append("Based on this situation, please provide your line of dialogue now.")

        user_prompt = "\n\n".join(user_prompt_parts)

        return system_prompt, user_prompt