"""LangChain 相容的資料綱要 (schema) 用於 orchestrator。

此檔案定義接收 Discord 請求與回傳回覆的 Pydantic 模型。
遵循 Google Python Style Guide。
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import BaseTool
from discord import Message


class OrchestratorRequest(BaseModel):
    """Request model received from Discord for orchestration.

    Attributes:
        message: The original Discord Message object.
        user_id: The Discord user ID who initiated the request.
        provider_name: Optional name of the LLM provider to use.
    """

    message: Message
    user_id: int
    provider_name: str | None = None

    class Config:
        # 設定允許任意類型 (discord.Message 非 Pydantic 型別)
        arbitrary_types_allowed = True


class OrchestratorResponse(BaseModel):
    """Response model returned by the orchestrator.

    Attributes:
        reply: The agent's reply or structured response (type varies by provider).
        tool_calls: Optional list of tool call records represented as dicts.
    """

    reply: Any | None = Field(default=None, description="Agent reply or structured response.")
    tool_calls: List[Dict] | None = Field(
        default=None, description="List of tool call records (each item is a dict)."
    )


__all__ = ["OrchestratorRequest", "OrchestratorResponse"]