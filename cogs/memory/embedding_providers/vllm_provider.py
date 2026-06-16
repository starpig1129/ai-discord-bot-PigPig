import asyncio
import logging

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings  # type: ignore

from ..vector.manager import register_embedding_provider
from addons.settings import MemoryConfig
from function import func

logger = logging.getLogger(__name__)


@register_embedding_provider("vllm")
def vllm_provider(settings: MemoryConfig) -> Embeddings:
    """
    vLLM embedding provider factory.

    vLLM exposes an OpenAI-compatible /v1/embeddings endpoint, so this routes
    through OpenAIEmbeddings with a custom base_url and a placeholder api_key.

    Expects settings to provide:
      - embedding_model_name (the --served-model-name vLLM was launched with)
      - vllm_url (e.g. http://127.0.0.1:8182)
    """
    try:
        model_name = getattr(settings, "embedding_model_name", None)
        if not model_name:
            raise ValueError("vllm provider requires embedding_model_name in settings")

        vllm_url = getattr(settings, "vllm_url", None)
        if not vllm_url:
            raise ValueError("vllm provider requires vllm_url in settings")

        return OpenAIEmbeddings(
            model=model_name,
            openai_api_base=f"{vllm_url}/v1",
            openai_api_key="EMPTY",
            check_embedding_ctx_length=False,
        )  # type: ignore

    except Exception as e:
        try:
            asyncio.create_task(func.report_error(e, "Failed to initialize vLLM embedding provider"))
        except Exception:
            logger.exception("Failed to schedule error report for vllm provider")
        raise
