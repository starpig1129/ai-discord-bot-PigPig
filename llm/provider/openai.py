from typing import Type

from langchain_openai import ChatOpenAI

from .base import BaseProvider


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI models."""
    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "openai"
    
    def get_model_class(self) -> Type:
        """Returns the ChatOpenAI class."""
        return ChatOpenAI