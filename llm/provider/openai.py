from langchain_openai import ChatOpenAI
from llm.provider.base import BaseProvider
import asyncio
from function import func
 
 
class OpenAIProvider(BaseProvider):
    """Provider for OpenAI generative models."""
 
    _llm_type: str = "openai"
 
    def __init__(self) -> None:
        """Initialize the provider and underlying model.
 
        Initialization failures are reported via func.report_error and do not raise.
        """
        self.model = None
        try:
            self.model = ChatOpenAI()
        except Exception as e:
            try:
                asyncio.create_task(func.report_error(e, "llm.provider.openai: initialization failed"))
            except Exception:
                print(f"[DEBUG] llm.provider.openai: initialization failed: {e}")

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "openai"

    @property
    def model_name(self) -> str:
        """Return the model name used by this provider."""
        return 'GPT-5-nano'
    
    def get_chat_model(self) -> ChatOpenAI:
        """Return the underlying ChatOpenAI model."""
        return self.model
__all__ = ["OpenAIProvider"]