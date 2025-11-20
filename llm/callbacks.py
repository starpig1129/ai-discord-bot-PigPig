from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from llm.utils.send_message import safe_edit_message


class ToolFeedbackCallbackHandler(AsyncCallbackHandler):
    """Callback handler for providing feedback during tool execution."""

    def __init__(
        self,
        message_edit: Any,
        language_manager: Any,
        guild_id: str
    ):
        self.message_edit = message_edit
        self.language_manager = language_manager
        self.guild_id = guild_id

    async def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when tool starts running."""
        tool_name = serialized.get("name", "Unknown Tool")
        
        # Try to get specific message for this tool
        msg = self.language_manager.translate(
            self.guild_id,
            "system", "chat_bot", "responses", "tools", tool_name
        )
        
        # Check if translation was found
        if "Translation not found" in msg or "TRANSLATION_ERROR" in msg:
            # Fallback to default tool message
            status_msg = self.language_manager.translate(
                self.guild_id,
                "system", "chat_bot", "responses", "tools", "default",
                tool_name=tool_name
            )
        else:
            status_msg = msg
        
        await safe_edit_message(self.message_edit, status_msg)
