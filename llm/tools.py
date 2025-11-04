"""Factory for LangChain tools based on user ID."""

from typing import List, cast
from langchain_core.tools import BaseTool, tool

@tool
def get_user_name(user_id: int) -> str:
    """Get a user's display name (example tool).
    Currently returns a hard-coded value; can be extended to query a database.
    """
    return "使用者名稱"

def get_tools(user_id: int) -> List[BaseTool]:
    """Return a list of tools available to the given user ID.

    Currently always returns the `get_user_name` tool.

    Args:
        user_id: The ID of the user.

    Returns:
        A list of BaseTool objects available for the user.
    """
    # TODO: Customize toolset based on user_id, permissions, etc.
    # The `@tool` decorator may return either a callable or a BaseTool object
    # depending on the LangChain version; use a runtime cast to satisfy static
    # type checkers while preserving runtime flexibility.
    return cast(List[BaseTool], [get_user_name])