"""Orchestrator: 使用 LangChain agent 處理來自 Discord 的訊息。

此模組負責整合 ProviderManager、工具列表，並使用
create_tool_calling_agent + AgentExecutor 執行 LLM 代理流程。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from discord import Message
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware

from llm.model_manager import ModelManager
from llm.tools import get_tools
from llm.schema import OrchestratorResponse
from function import func

class Orchestrator:
    """核心 Orchestrator，將 Discord 訊息路由到 LangChain Agent 並回傳結果。

    使用者的錯誤與異常會透過 `func.report_error` 記錄，確保錯誤可追蹤。
    """

    def __init__(self) -> None:
        """初始化 ModelManager。"""
        self.model_manager = ModelManager()

    async def handle_message(self, request: Message) -> OrchestratorResponse:
        """處理傳入的 Discord 訊息並回傳 OrchestratorResponse。

        流程：
        1. 選擇 LLM provider（若 request.provider_name 未指定，則選第一個可用 provider）
        2. 取得該使用者可用的 tools
        3. 建立 ChatPromptTemplate、agent 與 AgentExecutor
        4. 非同步執行 agent 並解析回傳結果

        Args:
            request: 來自 Discord 的 OrchestratorRequest

        Returns:
            OrchestratorResponse: 包含回覆文字與 (可選) 工具呼叫紀錄
        """
        try:
            tool_list = get_tools(request.user_id)
            info_model = self.model_manager.get_model("info_model")

            info_agent = create_agent(
                model=info_model,
                tools=tool_list,
                middleware=[
                    ModelCallLimitMiddleware(
                        run_limit=1,
                        exit_behavior="end"
                    )
                ]
            )
            info_result = await info_agent.ainvoke({"input": request.content})

        except Exception as e:
            # 非同步回報錯誤並重新拋出以便上層處理
            asyncio.create_task(func.report_error(e, "info_agent failed"))
            raise

        # 建立 prompt（包含 system 與 human，human 含 agent_scratchpad 變數）
        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    SystemMessage(content="You are a helpful assistant for Discord users."),
                    HumanMessage(content="{input}\n\n{agent_scratchpad}"),
                ]
            )
        except Exception as e:
            asyncio.create_task(func.report_error(e, "llm.orchestrator: failed to build prompt"))


__all__ = ["Orchestrator"]