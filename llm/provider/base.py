from abc import ABC, abstractmethod
from typing import Type

class BaseProvider(ABC):
    """An abstract base class for LLM providers."""
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g. 'openai', 'google')."""
        
    @abstractmethod
    def get_model_class(self) -> Type:
        """
        Gets the model class for the provider.

        Returns:
            The class of the language model (e.g., ChatOpenAI).
        """
        pass