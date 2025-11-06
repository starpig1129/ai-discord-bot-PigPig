"""Orchestrator: 使用 LangChain agent 處理來自 Discord 的訊息。

此模組負責整合 ProviderManager、工具列表，並使用
create_tool_calling_agent + AgentExecutor 執行 LLM 代理流程。
"""
from __future__ import annotations

import asyncio
from typing import Any

from discord import Message
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware

from llm.model_manager import ModelManager
from llm.tools_factory import get_tools
from llm.schema import OrchestratorResponse, OrchestratorRequest
from llm.utils.send_message import send_message
from function import func


class Orchestrator:
    """核心 Orchestrator，將 Discord 訊息路由到 LangChain Agent 並回傳結果。

    使用者的錯誤與異常會透過 `func.report_error` 記錄，確保錯誤可追蹤。
    """

    def __init__(self) -> None:
        """初始化 ModelManager。"""
        self.model_manager = ModelManager()

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

            info_agent = create_agent(
                model=info_model,
                tools=tool_list,
                system_prompt="You are a helpful assistant for Discord users.",
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
                system_prompt="You are a helpful assistant for Discord users.",
                middleware=[ModelCallLimitMiddleware(run_limit=1, exit_behavior="end"), fallback]  # type: ignore[arg-type]
            )
            info_message = info_result["messages"][-1] 
            # Stream tokens from the agent and delegate message handling to send_message.
            # send_message will create an initial "processing" message if needed and
            # will edit/send messages as tokens arrive.
            message_result = ""
            streamer = message_agent.astream(
                {"messages": [HumanMessage(content=info_message.content)]},
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