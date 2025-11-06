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

from llm.model_manager import ModelManager
from llm.tools_factory import get_tools
from llm.schema import OrchestratorResponse, OrchestratorRequest
from llm.utils.send_message import send_message
from function import func
from .prompting.system_prompt import get_system_prompt
from addons.settings import prompt_config


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
        """從 addons/settings.py 構建 info_agent 系統提示詞。

        Args:
            bot_id: Discord 機器人 ID
            message: Discord 訊息物件

        Returns:
            完整的系統提示詞
        """
        try:
            # 從 prompt_config 取得 info_agent YAML 配置
            info_config = prompt_config.info_agent
            
            if not info_config:
                return self._get_info_agent_fallback_prompt(bot_id)
            
            # 構建基本提示詞
            base_instruction = info_config.get("base", {}).get("core_instruction", "")
            
            # 構建角色描述
            role_sections = []
            if "role" in info_config:
                role_data = info_config["role"]
                if "primary_function" in role_data:
                    role_sections.append("Primary Functions:")
                    for func_item in role_data["primary_function"]:
                        role_sections.append(f"- {func_item}")
                
                if "responsibilities" in role_data:
                    role_sections.append("\nResponsibilities:")
                    for resp in role_data["responsibilities"]:
                        role_sections.append(f"- {resp}")
            
            # 構建分析原則
            principles_sections = []
            if "analysis_principles" in info_config:
                principles = info_config["analysis_principles"]
                if "message_understanding" in principles:
                    principles_sections.append("Message Understanding:")
                    for principle in principles["message_understanding"]:
                        principles_sections.append(f"- {principle}")
                
                if "tool_selection" in principles:
                    principles_sections.append("\nTool Selection:")
                    for principle in principles["tool_selection"]:
                        principles_sections.append(f"- {principle}")
            
            # 組合完整提示詞
            prompt_parts = [
                base_instruction,
                "\n" + "\n".join(role_sections) if role_sections else "",
                "\n" + "\n".join(principles_sections) if principles_sections else "",
                "\nOutput Format:",
                "- Provide a brief summary of the user's intent",
                "- List any tools or resources that might be helpful",
                "- Flag any special considerations or concerns",
                "- Keep analysis focused and actionable",
            ]
            
            return "\n".join(filter(None, prompt_parts))
            
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
            message_pair = self.model_manager.get_model("info_model")
            if message_pair is None:
                raise RuntimeError("info_model not available")
            info_model, fallback = message_pair
            if info_model is None and fallback is None:
                raise RuntimeError("info_model not available")

            # 從 addons/settings.py 載入 info_agent 系統提示詞
            info_system_prompt = self._build_info_agent_prompt(
                bot_id=bot.user.id,
                message=message
            )
            
            info_agent = create_agent(
                model=info_model,
                tools=tool_list,
                system_prompt=info_system_prompt,
                middleware=[
                    ModelCallLimitMiddleware(run_limit=1, exit_behavior="end"),
                    fallback,
                ],  # type: ignore[arg-type]
            )

            info_result = await info_agent.ainvoke(
                {"messages": [HumanMessage(content=message.content)]},
            )
        except Exception as e:
            asyncio.create_task(func.report_error(e, "info_agent failed"))
            raise

        try:
            message_pair = self.model_manager.get_model("message_model")
            if message_pair is None:
                raise RuntimeError("message_model not available")
            message_model, fallback = message_pair
            if message_model is None and fallback is None:
                raise RuntimeError("message_model not available")
            
            message_agent = create_agent(
                model=message_model,
                tools=[],
                system_prompt=get_system_prompt(bot.user.id, message),
                middleware=[ModelCallLimitMiddleware(run_limit=1, exit_behavior="end"), fallback]  # type: ignore[arg-type]
            )
            info_message = info_result["messages"][-1] 

            
            message_result = ""
            streamer = message_agent.astream(
                {"messages": [AIMessage(content=info_message.content), HumanMessage(content=message.content)]},
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