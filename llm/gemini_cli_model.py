"""LangChain ChatModel wrapper using the Google Gemini SDK.

Provides a ``ChatGeminiCLI`` class that utilizes the new `google-genai`
Python SDK. This replaces the old subprocess-based CLI approach to improve
performance, avoid OS limits with large prompts, and fix timeout issues.

Also exports ``resolve_model()`` for intercepting ``gemini_cli:*`` model
strings at any ``create_agent`` call site.
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator, Iterator, List, Optional, Union, Dict

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field
from pydantic import PrivateAttr

# Attempt to import google-genai
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

logger = logging.getLogger(__name__)


class ChatGeminiCLI(BaseChatModel):
    """LangChain chat model wrapper around the Google Gemini SDK.
    
    This replaces the Node.js CLI subprocess with direct API calls via
    `google-genai`, retaining the same Langchain wrapper interface.
    """

    model: str = Field(
        default="gemini-3.0-flash",
        description="Model name format for Gemini. 'auto' defaults to 3.0 flash.",
    )
    temperature: float = Field(
        default=0.7,
        description="Temperature for generation.",
    )
    
    # Private client initialized once
    _client: Any = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if genai is None:
            raise ImportError(
                "Could not import google.genai python package. "
                "Please install it with `pip install google-genai`."
            )
        
        # Read API key explicitly from the same variables the CLI used
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if api_key:
            self._client = genai.Client(api_key=api_key)
        else:
            logger.warning("No GEMINI_API_KEY or GOOGLE_API_KEY found in environment! Deferring to SDK ADC/default auth.")
            self._client = genai.Client()

    @property
    def _llm_type(self) -> str:
        return "gemini-cli-sdk" # Keeps legacy name spirit but signifies SDK

    def _resolve_model_name(self) -> str:
        """Resolve model name. 'auto' translates to gemini-3.0-flash."""
        if self.model == "auto":
            return "gemini-3.0-flash"
        return self.model

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:
        """Stub for tool binding since this bare-bones SDK wrapper does not
        support tool parsing / function calling execution yet.
        
        Returning `self` allows LangChain to wrap it inside tool-enabled graphs
        (like info_agent) without raising NotImplementedError. The agent simply
        receives plain text instead of tool calls, safely exiting the loop.
        """
        return self

    @staticmethod
    def _format_messages(messages: List[BaseMessage]) -> str:
        """Combine all messages into a single string for the payload.

        Passes through ALL messages (system, human, AI) transparently.
        """
        text_parts = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if isinstance(msg, SystemMessage):
                text_parts.append(f"[System Instruction]\n{content}\n")
            elif isinstance(msg, HumanMessage):
                text_parts.append(f"[User]\n{content}\n")
            elif isinstance(msg, AIMessage):
                text_parts.append(f"[Model]\n{content}\n")
        return "\n".join(text_parts).strip()

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Execute Gemini SDK synchronously."""
        prompt = self._format_messages(messages)
        model_name = self._resolve_model_name()
        
        config_args = {"temperature": self.temperature}
        if stop:
            config_args["stop_sequences"] = stop
        
        try:
            response = self._client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**config_args)
            )
            output = response.text or ""
        except Exception as e:
            logger.error(f"Gemini SDK Error: {e}")
            raise RuntimeError(f"Gemini SDK failed: {e}") from e

        if not output:
             logger.warning("Gemini SDK returned empty output")
             raise RuntimeError("Gemini SDK returned empty response")

        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=output))]
        )

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Execute Gemini SDK asynchronously."""
        prompt = self._format_messages(messages)
        model_name = self._resolve_model_name()
        
        config_args = {"temperature": self.temperature}
        if stop:
            config_args["stop_sequences"] = stop
            
        try:
            response = await self._client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**config_args)
            )
            text = response.text or ""
        except Exception as e:
            logger.error(f"Gemini SDK async error: {e}")
            raise RuntimeError(f"Gemini SDK async failed: {e}") from e

        if not text:
            logger.warning("Gemini SDK returned empty asynchronous output.")
            raise RuntimeError("Gemini SDK returned empty response")

        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream generation synchronously."""
        prompt = self._format_messages(messages)
        model_name = self._resolve_model_name()
        
        config_args = {"temperature": self.temperature}
        if stop:
            config_args["stop_sequences"] = stop
            
        try:
            response_stream = self._client.models.generate_content_stream(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**config_args)
            )
            for chunk in response_stream:
                text = chunk.text or ""
                if text:
                    yield ChatGenerationChunk(message=AIMessageChunk(content=text))
                    if run_manager:
                        run_manager.on_llm_new_token(text)
        except Exception as e:
            logger.error(f"Gemini SDK streaming Error: {e}")
            raise RuntimeError(f"Gemini SDK streaming failed: {e}") from e

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Stream generation asynchronously."""
        prompt = self._format_messages(messages)
        model_name = self._resolve_model_name()
        
        config_args = {"temperature": self.temperature}
        if stop:
            config_args["stop_sequences"] = stop
            
        try:
            response_stream = await self._client.aio.models.generate_content_stream(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**config_args)
            )
            async for chunk in response_stream:
                text = chunk.text or ""
                if text:
                    yield ChatGenerationChunk(message=AIMessageChunk(content=text))
                    if run_manager:
                        await run_manager.on_llm_new_token(text)
        except Exception as e:
            logger.error(f"Gemini SDK async streaming Error: {e}")
            raise RuntimeError(f"Gemini SDK async streaming failed: {e}") from e


def resolve_model(model_name: str, cache: bool = True) -> Any:
    """Returns a ChatGeminiCLI instance configured for the specific model.
    """
    if ":" in model_name:
        base, model_id = model_name.split(":", 1)
        return ChatGeminiCLI(model=model_id, temperature=0.7)
    return ChatGeminiCLI(model=model_name, temperature=0.7)
