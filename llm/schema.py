"""LangChain compatible data schemas.

This file defines the Pydantic models for receiving Discord requests and returning responses.
"""

from __future__ import annotations

from typing import Any, Dict, List
from dataclasses import dataclass
from pydantic import BaseModel, Field

from discord import Message
@dataclass
class OrchestratorRequest:
    bot: Any
    message: Message
    logger: Any

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


__all__ = ["OrchestratorResponse"]