"""Orchestrator: 使用 LangChain agent 處理來自 Discord 的訊息。

此模組負責整合 ProviderManager、工具列表，並使用
create_tool_calling_agent + AgentExecutor 執行 LLM 代理流程。
"""
from __future__ import annotations

import asyncio
from typing import Any

from discord import Message
from langchain.tools import ToolRuntime
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware

from llm.model_manager import ModelManager
from llm.tools_factory import get_tools
from llm.schema import OrchestratorResponse
from llm.utils.send_message import send_message
from function import func

class Orchestrator:
    """核心 Orchestrator，將 Discord 訊息路由到 LangChain Agent 並回傳結果。

    使用者的錯誤與異常會透過 `func.report_error` 記錄，確保錯誤可追蹤。
    """

    def __init__(self) -> None:
        """初始化 ModelManager。"""
        self.model_manager = ModelManager()

    async def handle_message(self, bot: Any, message: Message, logger: Any) -> OrchestratorResponse:
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
            
            tool_list = get_tools(user, guid=guild)

            info_model = self.model_manager.get_model("info_model")
            if info_model is None:
                raise RuntimeError("info_model not available")
            
            info_agent = create_agent(
                model=info_model,
                tools=tool_list,
                context=ToolRuntime(bot=bot, message=message, logger=logger),  # type: ignore[arg-type]
                system_prompt="You are a helpful assistant for Discord users.",
                middleware=[ModelCallLimitMiddleware(run_limit=1, exit_behavior="end")]  # type: ignore[arg-type]
            )

            info_result = await info_agent.ainvoke({"messages": [{"role": "user", "content": message.content}]})

        except Exception as e:
            # 非同步回報錯誤並重新拋出以便上層處理
            asyncio.create_task(func.report_error(e, "info_agent failed"))
            raise
        try:
            message_models = self.model_manager.get_model("message_models")
            if message_models is None:
                raise RuntimeError("message_models not available")
            
            message_agent = create_agent(
                model=message_models,
                tools=tool_list,
                context=ToolRuntime(bot=bot, message=message, logger=logger),  # type: ignore[arg-type]
                middleware=[ModelCallLimitMiddleware(run_limit=1, exit_behavior="end")]  # type: ignore[arg-type]
            )

            # 從 info_result 嘗試擷取可當作下一階段輸入的文字
            if isinstance(info_result, dict):
                output = info_result.get("output") or info_result.get("text") or info_result.get("content") or str(info_result)
            else:
                output = str(info_result)

            # Stream tokens from the agent and delegate message handling to send_message.
            # send_message will create an initial "processing" message if needed and
            # will edit/send messages as tokens arrive.
            message_result = ""
            streamer = message_agent.stream(
                {"messages": [{"role": "user", "content": output}]},
                stream_mode="values"
            )
            # 傳入 bot 以避免模組層級依賴 main.bot
            message_result = await send_message(bot, None, message, streamer)


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