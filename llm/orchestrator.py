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

from llm.providers import ProviderManager
from llm.tools import get_tools
from llm.schema import OrchestratorResponse
from function import func

class Orchestrator:
    """核心 Orchestrator，將 Discord 訊息路由到 LangChain Agent 並回傳結果。

    使用者的錯誤與異常會透過 `func.report_error` 記錄，確保錯誤可追蹤。
    """

    def __init__(self) -> None:
        """初始化 ProviderManager。"""
        self.provider_manager = ProviderManager()

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
        # 選擇提供商
        provider = None
        try:
            if request.provider_name is not None:
                provider = self.provider_manager.get_provider(request.provider_name)
                if provider is None:
                    raise ValueError(f"provider '{request.provider_name}' not found")
            else:
                providers = self.provider_manager.list_providers()
                if not providers:
                    raise ValueError("no providers available")
                provider_name = providers[0]
                provider = self.provider_manager.get_provider(provider_name)
                if provider is None:
                    raise ValueError(f"provider '{provider_name}' could not be instantiated")
        except Exception as e:
            # 非同步回報錯誤並重新拋出以便上層處理
            asyncio.create_task(func.report_error(e, "llm.orchestrator: provider selection failed"))
            raise

        # 取得工具清單
        try:
            tools = get_tools(request.user_id)
        except Exception as e:
            asyncio.create_task(func.report_error(e, "llm.orchestrator: failed to get tools"))
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
            raise

        # 建立 agent 與 executor
        try:
            agent = create_tool_calling_agent(llm=provider, tools=tools, prompt=prompt)
            agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        except Exception as e:
            asyncio.create_task(func.report_error(e, "llm.orchestrator: failed to create agent"))
            raise

        # 執行 agent（非同步）
        try:
            call_input: Dict[str, Any] = {"input": request.message.content, "agent_scratchpad": ""}
            result = await agent_executor.ainvoke(call_input)
        except Exception as e:
            asyncio.create_task(func.report_error(e, "llm.orchestrator: agent execution failed"))
            raise

        # 解析結果
        content: str
        tool_calls: Optional[List[Dict]] = None
        try:
            if isinstance(result, str):
                content = result
            elif isinstance(result, dict):
                # 支援多種可能的欄位命名
                content = (
                    result.get("output")
                    or result.get("output_text")
                    or result.get("text")
                    or str(result)
                )
                tool_calls = result.get("tool_calls") or result.get("tool_calls_list")
            elif hasattr(result, "output"):
                content = getattr(result, "output")
            elif hasattr(result, "output_text"):
                content = getattr(result, "output_text")
            else:
                content = str(result)
        except Exception as e:
            asyncio.create_task(func.report_error(e, "llm.orchestrator: failed to parse agent result"))
            raise

        return OrchestratorResponse(content=content, tool_calls=tool_calls)


__all__ = ["Orchestrator"]