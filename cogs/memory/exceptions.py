# cogs/memory/exceptions.py

class MemorySystemError(Exception):
    """Base exception for the memory system."""
    pass

class DatabaseError(MemorySystemError):
    """Related to database operations."""
    pass

class VectorOperationError(MemorySystemError):
    """Related to vector store operations like add or upsert."""
    pass

class SearchError(MemorySystemError):
    """Related to search or query operations in the vector store."""
    pass

class IndexIntegrityError(VectorOperationError):
    """Related to index creation or integrity in the vector store."""
    pass

class DiscordAPIError(MemorySystemError):
    """Related to errors when fetching data from the Discord API."""
    pass