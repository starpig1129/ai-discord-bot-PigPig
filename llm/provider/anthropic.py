from typing import Type
from langchain_anthropic import ChatAnthropic
from .base import BaseProvider

class AnthropicProvider(BaseProvider):
    """Provider for Anthropic models."""
    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "anthropic"
    
    def get_model_class(self) -> Type:
        """Returns the ChatAnthropic class."""
        return ChatAnthropic