"""Google LLM provider using LangChain's ChatGoogleGenerativeAI.

This module provides GoogleProvider which wraps the ChatGoogleGenerativeAI model
and adapts its outputs into langchain_core's ChatResult/ChatGeneration types.
"""

from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI

from addons.tokens import tokens
from llm.provider.base import BaseProvider
import os


class GoogleProvider(BaseProvider):
    """Provider for Google generative models (Gemini)."""

    _llm_type: str = "google"

    def __init__(self) -> None:
        """Initialize the provider and underlying model.

        Reads the GOOGLE_API_KEY environment variable and raises ValueError if it
        is not set. Initializes ChatGoogleGenerativeAI with the desired model.
        """
        api_key = tokens.google_api_key
        if api_key is None:
            raise ValueError("Environment variable GOOGLE_API_KEY is not set")
        # Ensure the API key is available to the underlying library via env.
        os.environ["GOOGLE_API_KEY"] = api_key

        # Initialize the LangChain Google generative model.
        self.model = ChatGoogleGenerativeAI()

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