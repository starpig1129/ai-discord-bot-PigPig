"""Google LLM provider using LangChain's ChatGoogleGenerativeAI.

This module provides GoogleProvider which wraps the ChatGoogleGenerativeAI model
and adapts its outputs into langchain_core's ChatResult/ChatGeneration types.
"""

from __future__ import annotations

from typing import List, Optional, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.messages import BaseMessage
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
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Environment variable GOOGLE_API_KEY is not set")
        # Ensure the API key is available to the underlying library via env.
        os.environ["GOOGLE_API_KEY"] = api_key

        # Initialize the LangChain Google generative model.
        self.model = ChatGoogleGenerativeAI(
            model="gemini-pro", convert_system_message_to_human=True
        )

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "google"

    @property
    def model_name(self) -> str:
        """Return the model name used by this provider."""
        return "gemini-pro"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Invoke the underlying model and convert the result to ChatResult.

        Args:
            messages: A list of BaseMessage objects to send to the model.
            stop: Optional list of stop tokens.
            **kwargs: Forwarded to the underlying model.invoke call.

        Returns:
            ChatResult containing one or more ChatGeneration entries constructed
            from the model's response.
        """
        # Call the underlying model. The ChatGoogleGenerativeAI.invoke method
        # typically returns an AIMessage-like object; adapt its content into
        # ChatGeneration / ChatResult.
        ai_response = self.model.invoke(messages, stop=stop, **kwargs)

        # Extract a textual representation from the AI response.
        if isinstance(ai_response, str):
            content = ai_response
        else:
            content = getattr(ai_response, "content", None) or getattr(
                ai_response, "text", None
            ) or str(ai_response)

        # Construct ChatGeneration. Prefer using the returned message object
        # directly when possible so role/meta are preserved.
        try:
            generation = ChatGeneration(message=ai_response)
        except Exception:
            # Fallback to a generation constructed from text only.
            generation = ChatGeneration(message=None)

        # Some ChatGeneration implementations may not accept an empty message;
        # attempt to set a text attribute if present.
        try:
            setattr(generation, "text", content)
        except Exception:
            # If the ChatGeneration API does not support setting 'text', ignore.
            pass

        return ChatResult(generations=[generation])