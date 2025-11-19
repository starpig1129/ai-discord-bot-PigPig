from typing import Optional
import asyncio

from langchain_core.embeddings import Embeddings

from ..vector.manager import register_embedding_provider
from addons.settings import MemoryConfig
from addons.logging import get_logger
from function import func

logger = get_logger(server_id="system", source=__name__)


@register_embedding_provider("base")
def base_provider(settings: MemoryConfig) -> Embeddings:
    """
    Base dummy embedding provider returning zero vectors.
    Useful for tests and local development when no real model is available.
    """
    class BaseEmbeddings(Embeddings):
        def __init__(self, dim: int = 8):
            self.dim = dim

        def embed_documents(self, texts):
            return [[0.0] * self.dim for _ in texts]

        def embed_query(self, text):
            return [0.0] * self.dim

    dim = getattr(settings, "embedding_dim", 8) or 8
    return BaseEmbeddings(dim)