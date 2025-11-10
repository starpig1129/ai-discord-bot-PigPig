import asyncio
import logging
from typing import Any

from langchain_core.embeddings import Embeddings

from ..vector.manager import register_embedding_provider
from addons.settings import MemoryConfig
from addons.tokens import tokens
from function import func

logger = logging.getLogger(__name__)


@register_embedding_provider("openai")
async def openai_provider(settings: MemoryConfig) -> Embeddings:
    """
    OpenAI embedding provider factory.

    Expects settings to provide:
      - openai_api_key
      - openai_model_name

    Returns a langchain_core compatible Embeddings instance.
    """
    try:
        api_key = getattr(tokens, "openai_api_key", None)
        model_name = getattr(settings, "embedding_model_name", None)
        if not api_key or not model_name:
            raise ValueError("openai provider requires openai_api_key and openai_model_name in settings")

        # Prefer langchain_core wrapper if available
        try:
            from langchain_openai import OpenAIEmbeddings  # type: ignore
            return OpenAIEmbeddings(model=model_name, openai_api_key=api_key)  # type: ignore
        except Exception as exc:
            # If wrapper not available, report and re-raise to allow fallback handling by caller
            asyncio.create_task(func.report_error(exc, "OpenAIEmbeddings wrapper not available"))
            raise
    except Exception as e:
        # Report and rethrow for caller to handle initialization failure
        try:
            asyncio.create_task(func.report_error(e, "Failed to initialize OpenAI embedding provider"))
        except Exception:
            logger.exception("Failed to schedule error report for openai provider init")
        raise