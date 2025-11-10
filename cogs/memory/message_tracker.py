# cogs/memory/message_tracker.py
# Compatibility shim that re-exports the refactored MessageTracker located under cogs.memory.services.

from cogs.memory.services.message_tracker import MessageTracker  # type: ignore