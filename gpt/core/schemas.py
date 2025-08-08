# -*- coding: utf-8 -*-
"""Pydantic models for strict validation of tool usage data structures."""

from typing import Any, Dict, List, Literal, Optional

import pydantic
from pydantic import BaseModel, Field, ValidationError

# Pydantic v2-friendly field constraints:
# - Use Field(..., min_length=1) for strings
# - Use Field(default=None, ge=..., le=...) for numeric ranges
# - Use List[Model] with Field(..., min_length=1) for non-empty lists

class ToolCall(BaseModel):
    """Represents a single, validated tool call from the LLM."""
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    arguments: Dict[str, Any]
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rationale: Optional[str] = None
    raw_text_span: Optional[str] = None
    selection_index: Optional[int] = None

    model_config = {
        "extra": "forbid",
    }


class ToolSelection(BaseModel):
    """Represents the full, validated tool selection block from the LLM."""
    model: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    tool_calls: List[ToolCall] = Field(..., min_length=1)
    selection_strategy: Literal["greedy", "top_p", "voting", "rule_based"]
    parsed_from: Literal["json_block", "fenced_code", "heuristic", "none"]
    parse_confidence: float = Field(..., ge=0.0, le=1.0)
    trace_id: str = Field(..., min_length=1)

    model_config = {
        "extra": "forbid",
    }

# Export validation error for easy access
PydanticValidationError = ValidationError