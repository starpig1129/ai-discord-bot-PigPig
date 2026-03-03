"""LangChain ChatModel wrapper using the Google Gemini CLI via subprocess.

Provides a ``ChatGeminiCLI`` class that invokes the global ``gemini``
Node.js command. This is used as a fallback to take advantage of Google One
AI Pro quotas when API Keys are not available or preferred.

Also exports ``resolve_model()`` for intercepting ``gemini_cli:*`` model
strings at any ``create_agent`` call site.
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import shlex
import subprocess
from typing import Any, AsyncIterator, Iterator, List, Optional, Union

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel as _BaseChatModel
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

logger = logging.getLogger(__name__)


class ChatGeminiCLI(BaseChatModel):
    """LangChain chat model wrapper around the Google Gemini CLI.
    
    This heavily relies on subprocess calls to `gemini prompt <text>`,
    meaning performance is bound by Node.js startup time and CLI execution speed.
    """

    model: str = Field(
        default="gemini-3.0-flash",
        description="Model name format for Gemini CLI. 'auto' defaults to 3.0 flash.",
    )
    temperature: float = Field(
        default=0.7,
        description="Not currently supported by raw gemini CLI.",
    )

    @property
    def _llm_type(self) -> str:
        return "gemini-cli"

    def _resolve_model_name(self) -> str:
        """Resolve model name. 'auto' is kept as-is for CLI's internal selection."""
        return self.model

    @staticmethod
    def _get_node20_env() -> str:
        """Finds Node >= v20 path in nvm and returns a PATH prepend string.

        Falls back to empty string if not using NVM or if v20/v22 isn't found.
        """
        nvm_base = os.path.expanduser("~/.nvm/versions/node")
        if os.path.isdir(nvm_base):
            for prefix in ["v22.*", "v20.*"]:
                matches = glob.glob(os.path.join(nvm_base, prefix))
                if matches:
                    matches.sort(reverse=True)
                    node_path = os.path.join(matches[0], "bin")
                    return f"PATH={node_path}:$PATH "
        return ""

    @staticmethod
    def _format_messages(messages: List[BaseMessage]) -> str:
        """Combine all messages into a single string for the CLI payload.

        Passes through ALL messages (system, human, AI) transparently,
        mirroring exactly what the API-based models receive from the
        orchestrator.
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
        """Execute gemini CLI synchronously."""
        prompt = self._format_messages(messages)

        try:
            safe_prompt = shlex.quote(prompt)
            env_prefix = self._get_node20_env()
            shell_cmd = f"{env_prefix}gemini prompt {safe_prompt}"
            
            result = subprocess.run(
                shell_cmd,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
                cwd='/tmp',  # Prevent CLI from reading project GEMINI.md
            )
            output = result.stdout.strip()
            # The CLI usually uses markdown styling headers or empty whitespace we strip out
        except subprocess.CalledProcessError as e:
            logger.error(f"Gemini CLI Error: {e.stderr}")
            raise RuntimeError(f"Gemini CLI failed: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise TimeoutError("Gemini CLI timed out generating response") from e

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
        """Execute gemini CLI asynchronously via asyncio subprocess."""
        prompt = self._format_messages(messages)
        safe_prompt = shlex.quote(prompt)
        env_prefix = self._get_node20_env()
        shell_cmd = f"{env_prefix}gemini prompt {safe_prompt}"

        proc = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd='/tmp',  # Prevent CLI from reading project GEMINI.md
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError("Gemini CLI async call timed out")

        if proc.returncode != 0:
            err_msg = stderr.decode() if stderr else "Unknown Error"
            logger.error(f"Gemini CLI Error: {err_msg}")
            raise RuntimeError(f"Gemini CLI failed: {err_msg}")

        text = stdout.decode().strip() if stdout else ""
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    # Note: Real token-by-token streaming is extremely hard to parse from TTY 
    # output of the raw `gemini` CLI. We simulate it by yielding the final output block.

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        content = result.generations[0].message.content
        yield ChatGenerationChunk(message=AIMessageChunk(content=str(content)))

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        result = await self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        content = result.generations[0].message.content
        yield ChatGenerationChunk(message=AIMessageChunk(content=str(content)))


from langchain.chat_models import init_chat_model

def resolve_model(model_str: str) -> Union[str, _BaseChatModel]:
    """Resolve a provider-qualified model string.

    If *model_str* starts with ``gemini_cli:``, return a ready-to-use
    ``ChatGeminiCLI`` instance.
    If it starts with ``google_genai:``, we instantiate it immediately
    with `max_retries=1` to prevent LangChain from hanging for ~22s
    when hitting 429 Quota Exceeded errors.
    Otherwise return the string unchanged so that ``init_chat_model``
    can handle it.
    """
    if model_str.startswith("gemini_cli:"):
        model_name = model_str.split(":", 1)[1]
        return ChatGeminiCLI(model=model_name)
    elif model_str.startswith("google_genai:"):
        try:
            return init_chat_model(model_str, max_retries=1)
        except Exception as e:
            logger.warning(f"Failed to pre-initialize {model_str} with max_retries: {e}")
            return model_str
    return model_str
