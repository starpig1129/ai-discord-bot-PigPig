import discord
from discord.ext import commands
import logging
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from enum import Enum

from .models import (
    StoryInstance, StoryWorld, StoryCharacter, Location, DialogueContext
)
from cogs.system_prompt.manager import SystemPromptManager
from cogs.language_manager import LanguageManager


class StoryPromptEngine:
    """Builds high-quality prompts for the layered AI agents in the story."""

    def __init__(self, bot: commands.Bot, system_prompt_manager: "SystemPromptManager"):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.system_prompt_manager = system_prompt_manager
        self.language_manager: Optional[LanguageManager] = self.bot.get_cog('LanguageManager')
        self.language_map = {
            "zh_TW": "Traditional Chinese",
            "zh_CN": "Simplified Chinese",
            "en_US": "English",
            "ja_JP": "Japanese"
        }

    async def build_gm_prompt(
        self,
        instance: StoryInstance,
        world: StoryWorld,
        characters: List[StoryCharacter],
        user_input: str,
        story_outlines: List[str],
    ) -> str:
        """Constructs the prompt for the Game Master (GM) Agent."""
        
        base_prompt = self.system_prompt_manager.get_effective_full_prompt(
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

        if story_outlines:
            prompt_parts.append("## Story Outline So Far")
            prompt_parts.append("This is the high-level plot outline, summarizing major arcs and events. Use this for strategic, long-term decisions.")
            outline_text = "\n".join([f"- {outline}" for outline in story_outlines])
            prompt_parts.append(outline_text)

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

    async def build_story_start_prompt(self, instance: StoryInstance, world: StoryWorld, characters: List[StoryCharacter]) -> str:
        """Constructs the prompt for the GM to generate the very first scene."""
        base_prompt = self.system_prompt_manager.get_effective_full_prompt(
            str(instance.channel_id), str(instance.guild_id)
        )
        if not base_prompt:
            self.logger.warning("No base_prompt available, using fallback GM system prompt for story start")
            base_prompt = self._get_fallback_gm_prompt()

        prompt_parts = [base_prompt]
        prompt_parts.append("## Task: Generate the Opening Scene")
        prompt_parts.append(
            "You are the Director (Game Master). Your task is to set the stage for a brand new story. "
            "Describe the initial setting, introduce the characters present, and establish the initial mood. "
            "Your output MUST be a single, valid JSON object conforming to the `GMActionPlan` schema. "
            "For this first scene, the `action_type` should almost always be `NARRATE`."
        )
        prompt_parts.append("## World & Scene Context")
        prompt_parts.append(f"### World: {world.world_name}")
        prompt_parts.append(f"**World Background:** {world.attributes.get('background', 'Not provided.')}")

        state_block = (
            f"**Starting Location:** {instance.current_location}\n"
            f"**Date:** {instance.current_date}\n"
            f"**Time:** {instance.current_time}"
        )
        prompt_parts.append(state_block)

        prompt_parts.append("### Characters to Introduce")
        if characters:
            char_lines = [
                f"- **{char.name}** ({'Player' if char.is_pc else 'NPC'}): {char.description} Status: {char.status}."
                for char in characters
            ]
            prompt_parts.append("\n".join(char_lines))
        else:
            prompt_parts.append("No specific characters are present at the start.")

        prompt_parts.append("## Final Instruction")
        prompt_parts.append("Generate the `GMActionPlan` JSON for the story's opening narration now.")

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
        self,
        character: StoryCharacter,
        gm_context: "DialogueContext",
        guild_id: int,
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
            # Ensure attributes are serializable
            safe_attrs = {k: str(v) for k, v in character.attributes.items()}
            attrs = ", ".join(f"{k}: {v}" for k, v in safe_attrs.items())
            system_prompt_parts.append(f"**Your Traits:** {attrs}")

        system_prompt_parts.append("## Core Instructions")
        system_prompt_parts.append(
            "You are a character in a story. Please respond in the first person, embodying your character's personality and background."
        )
        system_prompt_parts.append(
            "**IMPORTANT: Your entire output must be ONLY the dialogue text.** Do not include your character name, quotation marks, or any other formatting or explanations."
        )

        # Add language instruction
        if self.language_manager:
            lang_code = self.language_manager.get_server_lang(str(guild_id))
            language_name = self.language_map.get(lang_code, "English")
            language_instruction = f"Always answer in {language_name}."
            system_prompt_parts.append(language_instruction)
        
        system_prompt = "\n\n".join(system_prompt_parts)

        # --- User Prompt: Dynamic, Situational Context ---
        user_prompt_parts = []
        user_prompt_parts.append("## Current Situation & Task")
        user_prompt_parts.append(f"Your current motivation is: **{gm_context.motivation}**")
        user_prompt_parts.append(f"Your current emotional state is: **{gm_context.emotional_state}**")

        user_prompt_parts.append("\n## Your Task")
        user_prompt_parts.append(
            "The conversation history and relevant summaries are provided in the dialogue history. "
            "Based on your identity, the current situation, and the history, please provide your line of dialogue now."
        )

        user_prompt = "\n\n".join(user_prompt_parts)

        return system_prompt, user_prompt