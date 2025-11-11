from __future__ import annotations
import asyncio
from typing import Any
import json

from discord import Message
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, AgentMiddleware, hook_config

from llm.model_manager import ModelManager
from llm.tools_factory import get_tools
from llm.schema import OrchestratorResponse, OrchestratorRequest
from llm.utils.send_message import send_message
from function import func
from addons.settings import prompt_config
from .prompting.system_prompt import get_system_prompt

# New imports for context engineering
from llm.context_manager import ContextManager
from llm.memory.schema import SystemContext
from llm.memory.short_term import ShortTermMemoryProvider
from llm.memory.episodic import EpisodicMemoryProvider
from llm.memory.procedural import ProceduralMemoryProvider
from cogs.memory.interfaces.vector_store_interface import VectorStoreInterface
from cogs.memory.users.manager import SQLiteUserManager


class DirectToolOutputMiddleware(AgentMiddleware):
    @hook_config(can_jump_to=["end"])
    def after_tools(self, state, runtime):
        return {"jump_to": "end"}

class Orchestrator:
    """
    The core orchestrator that routes Discord messages to a LangChain Agent and returns the result.
    It now integrates a ContextManager to provide rich context to the LLM.
    """

    def __init__(self, bot: Any):
        """
        Initializes the ModelManager and the new ContextManager.
        Dependencies for memory providers are injected from the bot instance.
        """
        self.model_manager = ModelManager()
        
        # --- New: Initialize ContextManager and its providers ---
        # These dependencies are expected to be available on the bot object
        vector_store: VectorStoreInterface = getattr(bot, 'vector_store', None)
        user_manager: SQLiteUserManager = getattr(bot, 'user_manager', None)

        if not vector_store or not user_manager:
            # In a real scenario, you might want to handle this more gracefully
            # For now, we'll log a warning. The providers will fail if they are used.
            asyncio.create_task(func.report_error(
                Exception("Missing vector_store or user_manager on bot object for Orchestrator"),
                "Orchestrator.__init__"
            ))

        short_term_provider = ShortTermMemoryProvider(limit=15)
        episodic_provider = EpisodicMemoryProvider(vector_store=vector_store)
        procedural_provider = ProceduralMemoryProvider(user_manager=user_manager)

        self.context_manager = ContextManager(
            short_term_provider=short_term_provider,
            episodic_provider=episodic_provider,
            procedural_provider=procedural_provider,
        )
        # --- End of new section ---

    def _format_context_for_prompt(self, context: SystemContext) -> str:
        """
        Formats the SystemContext object into a structured string for the LLM prompt.
        """
        if not context:
            return ""

        parts = ["--- System Context ---"]

        # 1. Procedural Memory
        if context.procedural_memory and context.procedural_memory.user_info:
            user_info = context.procedural_memory.user_info
            proc_mem_parts = []
            if user_info.user_background:
                proc_mem_parts.append(f"User Background: {user_info.user_background}")
            if user_info.procedural_memory:
                proc_mem_parts.append(f"User Preferences: {user_info.procedural_memory}")
            if proc_mem_parts:
                parts.append("## Procedural Memory (User Info)\n" + "\n".join(proc_mem_parts))

        # 2. Episodic Memory
        if context.episodic_memory and context.episodic_memory.fragments:
            frag_strs = [f"- {frag.content} (source: {frag.metadata.get('jump_url')})" for frag in context.episodic_memory.fragments]
            parts.append("## Episodic Memory (Relevant Events)\n" + "\n".join(frag_strs))

        # 3. Short-Term Memory
        if context.short_term_memory and context.short_term_memory.messages:
            msg_strs = [
                f"[{msg['timestamp']}] {msg['author']}: {msg['content']}" 
                for msg in context.short_term_memory.messages
            ]
            parts.append("## Short-Term Memory (Recent Conversation)\n" + "\n".join(msg_strs))
        
        # 4. Current State
        parts.append(f"## Current State\n- Channel: #{context.current_channel_name}\n- Timestamp: {context.timestamp}")

        parts.append("--- End of System Context ---")
        
        return "\n\n".join(parts)


    def _build_info_agent_prompt(
        self, bot_id: int, message: Message
    ) -> str:
        """從 addons/settings 構建 info_agent 系統提示詞。

        Args:
            bot_id: Discord 機器人 ID
            message: Discord 訊息物件

        Returns:
            完整的系統提示詞
        """
        try:
            info_system_prompt = prompt_config.get_system_prompt('info_agent')
            if not info_system_prompt:
                asyncio.create_task(func.report_error(
                    Exception("info_agent system_prompt is empty"),
                    "building info_agent prompt"
                ))
                return self._get_info_agent_fallback_prompt(bot_id)
            return info_system_prompt
        except Exception as e:
            asyncio.create_task(func.report_error(e, "building info_agent prompt"))
            return self._get_info_agent_fallback_prompt(bot_id)

    def _get_info_agent_fallback_prompt(self, bot_id: int) -> str:
        """取得備用的 info_agent 提示詞。

        Args:
            bot_id: Discord 機器人 ID

        Returns:
            備用提示詞
        """
        return f"""You are an information analysis assistant helping a Discord chatbot <@{bot_id}>. Your role is to analyze user messages and extract key information.

Your responsibilities:
- Analyze user intent and message content
- Classify the type of query (question, command, conversation, etc.)
- Identify required tools or external resources
- Extract key entities and context from messages

Analysis Guidelines:
- Read the entire message carefully before drawing conclusions
- Consider context from previous conversations when available
- Identify the core request even if wrapped in casual language
- Determine which tools or capabilities might be needed

Output Format:
- Provide a brief summary of the user's intent
- List any tools or resources that might be helpful
- Flag any special considerations or concerns
- Keep analysis focused and actionable

Focus on understanding what the user actually needs and prepare a clear analysis for the response generation phase."""

    async def handle_message(
        self, bot: Any, message_edit: Message, message: Message, logger: Any
    ) -> OrchestratorResponse:
        
        try:
            system_context = await self.context_manager.build_context(message)
            formatted_context = self._format_context_for_prompt(system_context)
        except Exception as e:
            await asyncio.create_task(func.report_error(e, "ContextManager failed in Orchestrator"))
            formatted_context = "" # Fallback to no context on error
        try:
            user = getattr(message, "author", None)
            if user is None:
                raise ValueError("Discord message.author has no id")

            guild = getattr(message, "guild", None)
            if guild is None:
                raise ValueError("Discord message.guild is None")

            runtime_context = OrchestratorRequest(
                bot=bot, message=message, logger=logger
            )
            tool_list = get_tools(user, guid=guild, runtime=runtime_context)
            
            try:
                info_model, fallback = self.model_manager.get_model("info_model")
            except Exception as e:
                await func.report_error(e, "ModelManager.get_model failed for info_model")
                raise RuntimeError(f"Failed to get info_model: {e}") from e

            # --- Modified: Inject context into prompt ---
            info_system_prompt = self._build_info_agent_prompt(
                bot_id=bot.user.id,
                message=message
            )
            full_info_prompt = f"{formatted_context}\n\n{info_system_prompt}"
            # --- End of modification ---

            info_agent = create_agent(
                model=info_model,
                tools=tool_list,
                system_prompt=full_info_prompt, # Use the combined prompt
                middleware=[
                    DirectToolOutputMiddleware(),
                    fallback,
                ],
            )

            info_result = await info_agent.ainvoke(
                {"messages": [HumanMessage(content=message.content)]},
            )
        except Exception as e:
            await asyncio.create_task(func.report_error(e, "info_agent failed"))
            raise

        try:
            try:
                message_model, fallback = self.model_manager.get_model("message_model")
            except Exception as e:
                await func.report_error(e, "ModelManager.get_model failed for message_model")
                raise RuntimeError(f"Failed to get message_model: {e}") from e
            
            # --- Modified: Inject context into prompt ---
            message_system_prompt = prompt_config.get_system_prompt('message_agent')
            if not message_system_prompt:
                message_system_prompt = get_system_prompt(bot.user.id, message)
            
            full_message_prompt = f"{formatted_context}\n\n{message_system_prompt}"
            # --- End of modification ---
            
            message_agent = create_agent(
                model=message_model,
                tools=[],
                system_prompt=full_message_prompt, # Use the combined prompt
                middleware=[ModelCallLimitMiddleware(run_limit=1, exit_behavior="end"), fallback]
            )
            
            info_message = info_result["messages"]
            
            streamer = message_agent.astream(
                {"messages": info_message + [HumanMessage(content=message.content)]},
                stream_mode="messages"
            )
            message_result = await send_message(bot, message_edit, message, streamer)

        except Exception as e:
            await asyncio.create_task(func.report_error(e, "message_agent failed"))
            raise

        resp = OrchestratorResponse.construct()
        resp.reply = message_result
        resp.tool_calls = [
            {"tool": getattr(t, "name", repr(t)), "args": getattr(t, "args", None)}
            for t in tool_list
        ]
        return resp

__all__ = ["Orchestrator"]