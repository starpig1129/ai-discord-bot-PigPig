import asyncio
import logging

from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore

from ..vector_manager import register_embedding_provider
from addons.settings import MemoryConfig
from function import func

logger = logging.getLogger(__name__)


@register_embedding_provider("huggingface")
def huggingface_provider(settings: MemoryConfig) -> Embeddings:
    """
    Provider factory using langchain_huggingface.HuggingFaceEmbeddings.

    Expects settings to provide:
      - embedding_model_name

    Returns a langchain_core compatible Embeddings instance.
    """
    try:
        model_name = getattr(settings, "embedding_model_name", None)
        if not model_name:
            raise ValueError("huggingface provider requires huggingface_model_name or embedding_model_name in settings")

        # Construct and return the HuggingFaceEmbeddings wrapper
        return HuggingFaceEmbeddings(model_name=model_name)  # type: ignore
    except Exception as e:
        try:
            asyncio.create_task(func.report_error(e, "Failed to initialize HuggingFace embedding provider"))
        except Exception:
            logger.exception("Failed to schedule error report for huggingface provider")
        raise