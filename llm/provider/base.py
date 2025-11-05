"""Abstract base provider for LLM providers.

This module defines BaseProvider, an abstract base class compatible with
langchain's BaseChatModel. Concrete providers should implement the abstract
properties and the _generate method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from langchain.chat_models import BaseChatModel


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
    def get_chat_model(self) -> BaseChatModel:
        """Return the underlying chat model instance.
 
        Concrete providers that wrap another chat model (for example the Google
        provider) should return that underlying model instance here. Providers
        that are themselves chat models may return self.
        """
        raise NotImplementedError