from typing import Type

from langchain_openai import AzureChatOpenAI

from .base import BaseProvider


class AzureChatOpenAIProvider(BaseProvider):
    """Provider for Azure OpenAI models."""
    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "azure_openai"
    
    def get_model_class(self) -> Type:
        """Returns the AzureChatOpenAI class."""
        return AzureChatOpenAI