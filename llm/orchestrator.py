"""Orchestrator: 使用 LangChain agent 處理來自 Discord 的訊息。

此模組負責整合 ProviderManager、工具列表，並使用
create_tool_calling_agent + AgentExecutor 執行 LLM 代理流程。
"""
from __future__ import annotations

import asyncio
from typing import Any

from discord import Message
from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.agents.middleware import AgentMiddleware, hook_config

from llm.model_manager import ModelManager
from llm.tools_factory import get_tools
from llm.schema import OrchestratorResponse, OrchestratorRequest
from llm.utils.send_message import send_message
from function import func
from addons.settings import prompt_config
from .prompting.system_prompt import get_system_prompt


class DirectToolOutputMiddleware(AgentMiddleware):
    @hook_config(can_jump_to=["end"])
    def after_tools(self, state, runtime):
        # 工具執行後直接結束，不再調用 LLM
        return {"jump_to": "end"}

class Orchestrator:
    """核心 Orchestrator，將 Discord 訊息路由到 LangChain Agent 並回傳結果。

    使用者的錯誤與異常會透過 `func.report_error` 記錄，確保錯誤可追蹤。
    """

    def __init__(self) -> None:
        """初始化 ModelManager。"""
        self.model_manager = ModelManager()

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
            # 從 addons/settings 取得 info_agent system_prompt
            info_system_prompt = prompt_config.get_system_prompt('info_agent')
            
            if not info_system_prompt:
                asyncio.create_task(func.report_error(
                    Exception("info_agent system_prompt 為空"),
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
        """處理傳入的 Discord 訊息並回傳 OrchestratorResponse。

        流程：
        2. 取得該使用者可用的 tools
        3. 建立 ChatPromptTemplate、agent 與 AgentExecutor
        4. 非同步執行 agent 並解析回傳結果

        Args:
            message: 來自 Discord 的 Message 物件

        Returns:
            OrchestratorResponse: 包含回覆文字與 (可選) 工具呼叫紀錄
        """
        try:
            # 驗證 message.author 與 guild
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
            except ValueError as e:
                await asyncio.create_task(func.report_error(e, "info_model not configured"))
                raise RuntimeError(f"info_model 未正確配置: {e}") from e
            except Exception as e:
                await asyncio.create_task(func.report_error(e, "ModelManager.get_model failed for info_model"))
                raise RuntimeError(f"取得 info_model 失敗: {e}") from e

            # 從 config/prompt/info_agent.yaml 載入 info_agent 系統提示詞
            info_system_prompt = self._build_info_agent_prompt(
                bot_id=bot.user.id,
                message=message
            )
            info_agent = create_agent(
                model=info_model,
                tools=tool_list,
                system_prompt=info_system_prompt,
                middleware=[
                    DirectToolOutputMiddleware(),
                    fallback,
                ],  # type: ignore
            )

            info_result = await info_agent.ainvoke(
                {"messages": [HumanMessage(content=message.content)]},
            )
        except Exception as e:
            asyncio.create_task(func.report_error(e, "info_agent failed"))
            raise

        try:
            try:
                message_model, fallback = self.model_manager.get_model("message_model")
            except ValueError as e:
                await asyncio.create_task(func.report_error(e, "message_model not configured"))
                raise RuntimeError(f"message_model 未正確配置: {e}") from e
            except Exception as e:
                await asyncio.create_task(func.report_error(e, "ModelManager.get_model failed for message_model"))
                raise RuntimeError(f"取得 message_model 失敗: {e}") from e
            
            # 從 addons/settings 載入 message_agent 系統提示詞
            message_system_prompt = prompt_config.get_system_prompt('message_agent')
            if not message_system_prompt:
                asyncio.create_task(func.report_error(
                    Exception("message_agent system_prompt 為空"),
                    "building message_agent prompt"
                ))
                message_system_prompt = get_system_prompt(bot.user.id, message)
            
            message_agent = create_agent(
                model=message_model,
                tools=[],
                system_prompt=message_system_prompt,
                middleware=[ModelCallLimitMiddleware(run_limit=1, exit_behavior="end"), fallback]  # type: ignore
            )
            info_message = info_result["messages"]
            print(info_message)
            
            message_result = ""
            streamer = message_agent.astream(
                {"messages": info_message + [HumanMessage(content=message.content)]},
                stream_mode="messages"
            )
            # 傳入 bot 以避免模組層級依賴 main.bot
            message_result = await send_message(bot, message_edit, message, streamer)


        except Exception as e:
            # 非同步回報錯誤並重新拋出以便上層處理
            asyncio.create_task(func.report_error(e, "message_agent failed"))
            raise

        resp = OrchestratorResponse.construct()
        resp.reply = message_result
        resp.tool_calls = [
            {"tool": getattr(t, "name", repr(t)), "args": getattr(t, "args", None)}
            for t in tool_list
        ]
        return resp

__all__ = ["Orchestrator"]