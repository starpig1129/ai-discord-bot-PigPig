"""Abstract base provider for LLM providers.

This module defines BaseProvider, an abstract base class compatible with
langchain's BaseChatModel. Concrete providers should implement the abstract
properties and the _generate method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from langchain_core.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult


class BaseProvider(BaseChatModel, ABC):
    """Abstract base class for LLM providers.

    Subclasses must provide the provider and model names and implement the
    low-level _generate method required by BaseChatModel.
    """

    # Fixed LLM type identifier required by LangChain integrations.
    _llm_type: str = "base_provider"

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g. 'openai', 'google')."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name used by the provider."""

    @abstractmethod
    def _generate(self, messages: Any, stop: Optional[List[str]] = None) -> ChatResult:
        """Generate chat responses for the given messages.

        Args:
            messages: The input messages in a provider-specific format.
            stop: Optional list of stop tokens.

        Returns:
            A ChatResult instance describing the generated outputs.
        """
        raise NotImplementedError