import warnings
from .vector.manager import VectorManager

warnings.warn(
    "cogs.memory.vector_manager is deprecated. Please import from cogs.memory.vector.manager instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["VectorManager"]