from __future__ import annotations
import asyncio
from typing import Any

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

from llm.context_manager import ContextManager
from llm.memory.short_term import ShortTermMemoryProvider
from llm.memory.procedural import ProceduralMemoryProvider


class DirectToolOutputMiddleware(AgentMiddleware):
    @hook_config(can_jump_to=["end"])
    def after_tools(self, state, runtime):
        return {"jump_to": "end"}


class Orchestrator:
    """
    Simplified orchestrator per docs/plans/context_replan.md.
    Context formatting moved to ContextManager.get_context().
    """

    def __init__(self, bot: Any):
        """
        Initialize model manager and context manager.
        """
        self.model_manager = ModelManager()

        # Initialize providers using resources from bot
        cog = bot.get_cog("UserDataCog")
        user_manager = getattr(cog, "user_manager", None) if cog is not None else None

        if user_manager is None:
            asyncio.create_task(func.report_error(
                Exception("Missing user_manager on bot UserDataCog for Orchestrator"),
                "Orchestrator.__init__"
            ))

        short_term_provider = ShortTermMemoryProvider(limit=15)
        procedural_provider = ProceduralMemoryProvider(user_manager=user_manager)

        self.context_manager = ContextManager(
            short_term_provider=short_term_provider,
            procedural_provider=procedural_provider,
        )

    def _build_info_agent_prompt(self, bot_id: int, message: Message) -> str:
        """
        Build system prompt for info_agent from settings with fallback.
        """
        try:
            info_system_prompt = prompt_config.get_system_prompt('info_agent')
            if not info_system_prompt:
                asyncio.create_task(func.report_error(
                    Exception("info_agent system_prompt is empty"),
                    "Orchestrator._build_info_agent_prompt"
                ))
                return self._get_info_agent_fallback_prompt(bot_id)
            return info_system_prompt
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Orchestrator._build_info_agent_prompt"))
            return self._get_info_agent_fallback_prompt(bot_id)

    def _get_info_agent_fallback_prompt(self, bot_id: int) -> str:
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

    async def handle_message(self, bot: Any, message_edit: Message, message: Message, logger: Any) -> OrchestratorResponse:

        try:
            formatted_context = await self.context_manager.get_context(message)
        except Exception as e:
            await asyncio.create_task(func.report_error(e, "ContextManager.get_context failed in Orchestrator"))
            formatted_context = ""

        try:
            user = getattr(message, "author", None)
            if user is None:
                raise ValueError("Discord message.author has no id")

            guild = getattr(message, "guild", None)
            if guild is None:
                raise ValueError("Discord message.guild is None")

            runtime_context = OrchestratorRequest(bot=bot, message=message, logger=logger)
            tool_list = get_tools(user, guid=guild, runtime=runtime_context)

            try:
                info_model, fallback = self.model_manager.get_model("info_model")
            except Exception as e:
                await func.report_error(e, "ModelManager.get_model failed for info_model")
                raise RuntimeError(f"Failed to get info_model: {e}") from e

            info_system_prompt = self._build_info_agent_prompt(bot_id=bot.user.id, message=message)
            full_info_prompt = f"{formatted_context}\n\n{info_system_prompt}"
            print("Info Agent Prompt:\n", full_info_prompt)

            info_agent = create_agent(
                model=info_model,
                tools=tool_list,
                system_prompt=full_info_prompt,
                middleware=[DirectToolOutputMiddleware(), fallback],
            )

            info_result = await info_agent.ainvoke({"messages": [HumanMessage(content=message.content)]})
        except Exception as e:
            await asyncio.create_task(func.report_error(e, "info_agent failed"))
            raise

        try:
            try:
                message_model, fallback = self.model_manager.get_model("message_model")
            except Exception as e:
                await func.report_error(e, "ModelManager.get_model failed for message_model")
                raise RuntimeError(f"Failed to get message_model: {e}") from e

            message_system_prompt = prompt_config.get_system_prompt('message_agent')
            if not message_system_prompt:
                message_system_prompt = get_system_prompt(bot.user.id, message)

            full_message_prompt = f"{formatted_context}\n\n{message_system_prompt}"

            message_agent = create_agent(
                model=message_model,
                tools=[],
                system_prompt=full_message_prompt,
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
        resp.tool_calls = [{"tool": getattr(t, "name", repr(t)), "args": getattr(t, "args", None)} for t in tool_list]
        return resp


__all__ = ["Orchestrator"]