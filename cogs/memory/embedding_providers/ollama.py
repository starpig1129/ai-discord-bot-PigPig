import asyncio
import logging

from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings  # type: ignore

from ..vector.manager import register_embedding_provider
from addons.settings import MemoryConfig
from function import func

logger = logging.getLogger(__name__)


@register_embedding_provider("ollama")
def ollama_provider(settings: MemoryConfig) -> Embeddings:
    """
    Ollama embedding provider factory using langchain_ollama.OllamaEmbeddings.

    Expects settings to provide:
      - embedding_model_name
      - ollama_url (optional, if the client needs a custom endpoint)

    Returns a langchain_core compatible Embeddings instance.
    """
    try:
        model_name = getattr(settings, "embedding_model_name", None)
        if not model_name:
            raise ValueError("ollama provider requires ollama_model_name or embedding_model_name in settings")

        # Construct and return the OllamaEmbeddings wrapper
        # The constructor signature can vary; pass model_name and optional host if available.
        ollama_host = getattr(settings, "ollama_url", None)
        if ollama_host:
            return OllamaEmbeddings(model=model_name, base_url=ollama_host)  # type: ignore
        return OllamaEmbeddings(model=model_name)  # type: ignore

    except Exception as e:
        try:
            asyncio.create_task(func.report_error(e, "Failed to initialize Ollama embedding provider"))
        except Exception:
            logger.exception("Failed to schedule error report for ollama provider")
        raise