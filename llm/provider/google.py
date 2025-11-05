from typing import Type
from langchain_google_genai import ChatGoogleGenerativeAI
from .base import BaseProvider

class GoogleProvider(BaseProvider):
    """Provider for Google models."""
    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "google"
    
    def get_model_class(self) -> Type:
        """Returns the ChatGoogleGenerativeAI class."""
        return ChatGoogleGenerativeAI