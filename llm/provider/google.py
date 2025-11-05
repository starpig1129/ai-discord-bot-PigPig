"""Google LLM provider using LangChain's ChatGoogleGenerativeAI.

This module provides GoogleProvider which wraps the ChatGoogleGenerativeAI model
and adapts its outputs into langchain_core's ChatResult/ChatGeneration types.
"""

from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI
 
from addons.tokens import tokens
from llm.provider.base import BaseProvider
import os
import asyncio
from function import func
 
 
class GoogleProvider(BaseProvider):
    """Provider for Google generative models (Gemini)."""
 
    _llm_type: str = "google"
 
    def __init__(self) -> None:
        """Initialize the provider and underlying model.
 
        Reads the GEMINI_API_KEY from tokens; if missing report error and mark provider unavailable.
        Initialization failures are reported via func.report_error and do not raise.
        """
        self.model = None
        try:
            api_key = tokens.gemini_api_key
            if api_key is None:
                raise ValueError("Environment variable GEMINI_API_KEY is not set")
            # Ensure the API key is available to the underlying library via env.
            os.environ["GEMINI_API_KEY"] = api_key
            # Initialize the LangChain Google generative model.
            self.model = ChatGoogleGenerativeAI()
        except Exception as e:
            # 非同步回報錯誤並保持 provider 不可用（model = None）
            try:
                asyncio.create_task(func.report_error(e, "llm.provider.google: initialization failed"))
            except Exception:
                print(f"[DEBUG] llm.provider.google: initialization failed: {e}")

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "google"

    @property
    def model_name(self) -> str:
        """Return the model name used by this provider."""
        return "gemini-pro"
    def get_chat_model(self) -> ChatGoogleGenerativeAI:
        """Return the underlying ChatGoogleGenerativeAI model."""
        return self.model
__all__ = ["GoogleProvider"]