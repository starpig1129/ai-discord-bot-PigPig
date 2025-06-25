"""Custom exceptions for the story module."""

class StoryError(Exception):
    """Base exception for story-related errors."""
    pass

class StoryNotFoundError(StoryError):
    """Raised when a story instance is not found."""
    pass

class WorldNotFoundError(StoryError):
    """Raised when a world is not found."""
    pass

class CharacterNotFoundError(StoryError):
    """Raised when a character is not found."""
    pass

class StoryDatabaseError(StoryError):
    """Raised when there's a database-related error."""
    pass

class StoryPromptError(StoryError):
    """Raised when there's an error building the story prompt."""
    pass

class StoryGenerationError(StoryError):
    """Raised when there's an error generating the story response."""
    pass