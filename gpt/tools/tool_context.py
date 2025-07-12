from dataclasses import dataclass
from typing import Any

@dataclass
class ToolExecutionContext:
    """A context object holding resources for tool execution."""
    bot: Any
    message: Any
    message_to_edit: Any
    logger: Any