# MIT License
# Episodic memory retrieval tools for LLM integration.
from typing import Optional, Any, List
from datetime import datetime

from langchain.tools import tool

from function import func
from cogs.memory.vector_store_interface import MemoryFragment

class EpisodicMemoryTools:
    """Container for episodic memory tools bound to a runtime.

    This class provides LangChain-compatible tools that allow an LLM Agent
    to query the long-term episodic memory (semantic vector store) managed
    by the bot's VectorManager.

    Usage:
        tools = EpisodicMemoryTools(runtime).get_tools()
    """

    def __init__(self, runtime: Any):
        self.runtime = runtime
        self.logger = getattr(runtime, "logger", None)

    def _get_bot(self) -> Optional[Any]:
        """Safely retrieve the bot instance from the runtime."""
        bot = getattr(self.runtime, "bot", None)
        if not bot and self.logger:
            self.logger.error("Bot instance not found in runtime for EpisodicMemoryTools.")
        return bot

    def get_tools(self) -> List:
        """Return a list of LangChain tools (closures) bound to the runtime."""

        get_bot = self._get_bot

        @tool
        async def search_episodic_memory(
            vector_query: Optional[str] = None,
            keyword_query: Optional[str] = None,
            user_id: Optional[str] = None,
            channel_id: Optional[str] = None
        ) -> str:
            """
            Search episodic memory using semantic vectors and/or keyword matching.
    
            Use `vector_query` for broad, semantic searches (e.g., "what was our last discussion
            about database optimization?"). This will find conceptually similar fragments even if
            wording differs. Use `keyword_query` for exact-term searches (e.g., "Qdrant migration")
            to find memories containing precise tokens or phrases. You can provide both parameters
            together for a hybrid search that benefits from semantic recall and exact-match filtering.
    
            Parameters:
                vector_query (Optional[str]): Natural-language semantic query for vector search.
                keyword_query (Optional[str]): Exact-term query for keyword-based matching.
                user_id (Optional[str]): If provided, filter memories to the specified user.
                channel_id (Optional[str]): If provided, filter memories to the specified channel.
    
            Returns:
                str: A human-readable, plain-text summary of matched MemoryFragment entries,
                     including content and key metadata (author, timestamp, jump_url). If no
                     memories are found or an error occurs, returns an appropriate message.
            """
            bot = get_bot()
            if not bot:
                return "Error: Bot runtime is not available."
    
            try:
                vector_manager = getattr(bot, "vector_manager", None)
                if not vector_manager:
                    return "Error: VectorManager is not available on the bot."
    
                # Delegate to the vector store's search implementation, forwarding both
                # semantic and keyword parameters for a hybrid search when available.
                fragments: List[MemoryFragment] = await vector_manager.store.search(
                    vector_query=vector_query,
                    keyword_query=keyword_query,
                    user_id=user_id,
                    channel_id=channel_id
                )
    
                if not fragments:
                    return "No relevant memories found."
    
                formatted: List[str] = []
                for frag in fragments:
                    meta = frag.metadata or {}
                    author = meta.get("author", meta.get("author_id", "Unknown"))
                    timestamp = meta.get("timestamp")
                    if isinstance(timestamp, (int, float)):
                        try:
                            ts_str = datetime.utcfromtimestamp(float(timestamp)).isoformat() + "Z"
                        except Exception:
                            ts_str = str(timestamp)
                    else:
                        ts_str = str(timestamp or "Unknown Time")
    
                    jump_url = meta.get("jump_url", meta.get("jumpUrl", "N/A"))
                    fragment_id = meta.get("fragment_id", meta.get("id", "N/A"))
    
                    entry = (
                        f"Fragment ID: {fragment_id}\n"
                        f"Author: {author}\n"
                        f"Timestamp: {ts_str}\n"
                        f"Jump URL: {jump_url}\n"
                        f"Summary: {frag.content}"
                    )
                    formatted.append(entry)
    
                return "\n\n---\n\n".join(formatted)
    
            except Exception as e:
                # Consistent error reporting per project rules
                try:
                    await func.report_error(e, "search_episodic_memory failed")
                except Exception:
                    # If reporting itself fails, swallow to avoid raising in tool
                    pass
                return f"An error occurred while retrieving memories: {e}"

        return [retrieve_episodic_memory]