from langchain_anthropic import ChatAnthropic
from llm.provider.base import BaseProvider
import asyncio
from function import func
 
 
class AnthropicProvider(BaseProvider):
    """Provider for Anthropic generative models."""
 
    _llm_type: str = "anthropic"
 
    def __init__(self) -> None:
        """Initialize the provider and underlying model.
 
        Initialization failures are reported via func.report_error and do not raise.
        """
        self.model = None
        try:
            self.model = ChatAnthropic(model_name="claude-sonnent-4.5",timeout=120,stop=[""])
        except Exception as e:
            try:
                asyncio.create_task(func.report_error(e, "llm.provider.anthropic: initialization failed"))
            except Exception:
                print(f"[DEBUG] llm.provider.anthropic: initialization failed: {e}")

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "anthropic"

    @property
    def model_name(self) -> str:
        """Return the model name used by this provider."""
        return 'Claude-sonnent-4.5'

    def get_chat_model(self) -> ChatAnthropic:
        """Return the underlying ChatAnthropic model."""
        return self.model
__all__ = ["AnthropicProvider"]