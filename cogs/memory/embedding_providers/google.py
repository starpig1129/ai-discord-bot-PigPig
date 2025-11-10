import asyncio
import logging

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings  # type: ignore

from ..vector_manager import register_embedding_provider
from addons.settings import MemoryConfig
from addons.tokens import tokens
from function import func

logger = logging.getLogger(__name__)


@register_embedding_provider("google")
def google_genai_provider(settings: MemoryConfig) -> Embeddings:
    """
    Google Generative AI embeddings provider using langchain_google_genai.

    Expects settings to provide:
      - google_api_key
      - embedding_model_name

    Returns a langchain_core compatible Embeddings instance.
    """
    try:
        api_key = getattr(tokens, "google_api_key", None)
        model_name = getattr(settings, "embedding_model_name", None)
        if not api_key or not model_name:
            raise ValueError("google provider requires google_api_key and embedding_model_name in settings")

        return GoogleGenerativeAIEmbeddings(model=model_name, api_key=api_key)  # type: ignore
    except Exception as e:
        try:
            asyncio.create_task(func.report_error(e, "Failed to initialize Google Generative AI embedding provider"))
        except Exception:
            logger.exception("Failed to schedule error report for google provider")
        raise