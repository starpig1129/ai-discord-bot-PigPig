from langchain_ollama import ChatOllama
from llm.provider.base import BaseProvider
import asyncio
from function import func
 
 
class OllamaProvider(BaseProvider):
    """Provider for Ollama generative models."""
 
    _llm_type: str = "ollama"
 
    def __init__(self) -> None:
        """Initialize the provider and underlying model.
 
        Initialization failures are reported via func.report_error and do not raise.
        """
        self.model = None
        try:
            self.model = ChatOllama(model="GPT-oss-20b")
        except Exception as e:
            try:
                asyncio.create_task(func.report_error(e, "llm.provider.ollama: initialization failed"))
            except Exception:
                print(f"[DEBUG] llm.provider.ollama: initialization failed: {e}")

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "ollama"

    @property
    def model_name(self) -> str:
        """Return the model name used by this provider."""
        return 'GPT-oss-20b'

    def get_chat_model(self) -> ChatOllama:
        """Return the underlying ChatOllama model."""
        return self.model
__all__ = ["OllamaProvider"]