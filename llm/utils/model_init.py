"""Shared model instantiation helper with vLLM support via the OpenAI-compatible API."""
from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from addons.settings import llm_config


def create_model_instance(model_name: str, **kwargs: Any) -> BaseChatModel:
    """Create a LangChain chat model, routing 'vllm:' prefixed names through ChatOpenAI.

    init_chat_model has no native 'vllm' provider. Since vLLM exposes an
    OpenAI-compatible endpoint, 'vllm:<model>' is rewritten to 'openai:<model>'
    with base_url pointed at llm_config.vllm_url and a placeholder api_key
    (vLLM does not require a real key).

    Args:
        model_name: e.g. 'vllm:gemma4:26b', 'google_genai:gemini-2.5-flash', 'ollama:gemma4:26b'
        **kwargs:   Forwarded to the underlying constructor (max_retries, temperature, …)
    """
    if model_name.startswith("vllm:"):
        vllm_model = model_name[len("vllm:"):]
        return init_chat_model(
            f"openai:{vllm_model}",
            base_url=f"{llm_config.vllm_url}/v1",
            api_key="EMPTY",
            **kwargs,
        )
    return init_chat_model(model_name, **kwargs)


__all__ = ["create_model_instance"]
