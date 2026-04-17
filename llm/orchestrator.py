from __future__ import annotations
import asyncio
from typing import Any, List, Optional
import re

from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="llm.orchestrator")

from discord import Message
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, AgentMiddleware, hook_config

from llm.model_manager import ModelManager
from llm.tools_factory import get_tools
from llm.schema import OrchestratorResponse, OrchestratorRequest
from llm.utils.send_message import send_message, safe_edit_message
from function import func
from addons.settings import llm_config, prompt_config

_LLM_CALL_TIMEOUT_SECONDS: float = llm_config.llm_call_timeout
from .prompting.system_prompt import get_system_prompt
from .prompting.protected_prompt_manager import get_protected_prompt_manager

from llm.context_manager import ContextManager
from llm.memory.short_term import ShortTermMemoryProvider
from llm.memory.procedural import ProceduralMemoryProvider
from llm.memory.episodic import EpisodicMemoryProvider
from llm.callbacks import ToolFeedbackCallbackHandler
from llm.model_circuit_breaker import get_model_circuit_breaker


class DirectToolOutputMiddleware(AgentMiddleware):
    @hook_config(can_jump_to=["end"])
    def after_tools(self, state, runtime):
        return {"jump_to": "end"}


class Orchestrator:
    """
    Orchestrator updated to accept ContextManager's new return type.

    ContextManager.get_context now returns Tuple[str, List[BaseMessage]]:
      (procedural_context_str, short_term_msgs)

    Short-term memory (short_term_msgs) is passed directly as LangChain
    BaseMessage objects into agents' `messages` parameter to preserve
    structure and avoid double-serialization.
    """

    def __init__(self, bot: Any):
        """
        Initialize model manager and context manager.
        """
        self.model_manager = ModelManager()

        # Initialize providers using resources from bot
        cog = bot.get_cog("UserDataCog")
        user_manager = getattr(cog, "user_manager", None) if cog is not None else None

        from addons.settings import memory_config
        memory_enabled = getattr(memory_config, "enabled", True)

        if user_manager is None and memory_enabled:
            asyncio.create_task(
                func.report_error(
                    Exception("Missing user_manager on bot UserDataCog for Orchestrator"),
                    "Orchestrator.__init__",
                )
            )

        short_term_provider = ShortTermMemoryProvider(bot=bot, limit=15)
        procedural_provider = ProceduralMemoryProvider(user_manager=user_manager)

        # Episodic provider: only when memory is enabled and vector store is available
        episodic_provider: Optional[EpisodicMemoryProvider] = None
        if memory_enabled and getattr(bot, "vector_manager", None) is not None:
            episodic_provider = EpisodicMemoryProvider(bot=bot, top_k=3, max_chars=1500)

        self.context_manager = ContextManager(
            short_term_provider=short_term_provider,
            procedural_provider=procedural_provider,
            episodic_provider=episodic_provider,
        )

    def _build_info_agent_prompt(self, bot_id: int, message: Message) -> str:
        """
        Build system prompt for info_agent from settings with fallback.
        """
        try:
            info_system_prompt = prompt_config.get_system_prompt("info_agent")
            if not info_system_prompt:
                asyncio.create_task(
                    func.report_error(
                        Exception("info_agent system_prompt is empty"),
                        "Orchestrator._build_info_agent_prompt",
                    )
                )
                return self._get_info_agent_fallback_prompt(bot_id)
            return info_system_prompt
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Orchestrator._build_info_agent_prompt"))
            return self._get_info_agent_fallback_prompt(bot_id)

    def _get_info_agent_fallback_prompt(self, bot_id: int) -> str:
        return f"""You are an information analysis assistant helping a Discord chatbot <@{bot_id}>. Your role is to analyze user messages and extract key information.

Your responsibilities:
- Analyze user intent and message content
- Classify the type of query (question, command, conversation, etc.)
- Identify required tools or external resources
- Extract key entities and context from messages

Analysis Guidelines:
- Read the entire message carefully before drawing conclusions
- Consider context from previous conversations when available
- Identify the core request even if wrapped in casual language
- Determine which tools or capabilities might be needed

Output Format:
- Provide a brief summary of the user's intent
- List any tools or resources that might be helpful
- Flag any special considerations or concerns
- Keep analysis focused and actionable

Focus on understanding what the user actually needs and prepare a clear analysis for the response generation phase."""

    def _build_message_agent_prompt(self, bot_id: int, message: Message) -> str:
        """
        Build system prompt for message_agent using ProtectedPromptManager.
        
        System-level modules (Discord format, input parsing, memory system, etc.)
        are protected and always loaded from base_configs.
        Only customizable modules (identity, personality) can be overridden by users.
        
        Args:
            bot_id: Discord bot ID
            message: Discord message object
            
        Returns:
            Complete system prompt with protected system modules and customizable personality
        """
        try:
            # Get protected prompt manager
            protected_manager = get_protected_prompt_manager()
            
            # Try to get user customizations from database/settings
            # For now, we fallback to get_system_prompt for custom modules
            custom_modules = {}
            
            # Attempt to get channel/server-specific customizations
            # These should only affect customizable modules like identity, response_principles
            if message and hasattr(message, "channel") and hasattr(message, "guild"):
                try:
                    from .prompting.system_prompt import get_channel_system_prompt
                    channel_custom_prompt = get_channel_system_prompt(
                        str(message.channel.id), 
                        str(message.guild.id), 
                        str(bot_id), 
                        message
                    )
                    
                    # If channel has custom prompt, use it for customizable modules only
                    # The channel_custom_prompt should be parsed to extract only customizable parts
                    if channel_custom_prompt and channel_custom_prompt.strip():
                        # For now, if there's a channel custom prompt, we let it override
                        # BUT in future versions, we should parse it to separate customizable
                        # modules from protected ones
                        # For safety, we still use protected manager's compose method
                        pass
                        
                except Exception as exc:
                    asyncio.create_task(
                        func.report_error(exc, "Failed to get channel customizations for message_agent")
                    )
            
            # Compose prompt with protected system modules + customizable modules
            # Protected modules (output_format, input_parsing, memory_system, etc.) 
            # are ALWAYS from base_configs
            system_prompt = protected_manager.compose_system_prompt(
                custom_module_contents=custom_modules
            )
            
            # Apply dynamic replacements (bot_id, language, etc.)
            base_vars = protected_manager.get_base_variables()
            
            # Replace template variables
            try:
                from addons.tokens import tokens
                bot_owner_id = getattr(tokens, 'bot_owner_id', 0)
            except ImportError:
                bot_owner_id = 0
            
            system_prompt = system_prompt.replace('{bot_id}', str(bot_id))
            system_prompt = system_prompt.replace('{bot_owner_id}', str(bot_owner_id))
            system_prompt = system_prompt.replace('{bot_name}', base_vars.get('bot_name', '🐖🐖'))
            system_prompt = system_prompt.replace('{creator}', base_vars.get('creator', '星豬'))
            system_prompt = system_prompt.replace('{environment}', base_vars.get('environment', 'Discord server'))
            
            # Apply language replacements if available
            if message and message.guild:
                try:
                    bot_instance = message.guild.me._state._get_client()
                    lang_manager = bot_instance.get_cog("LanguageManager")
                    if lang_manager:
                        guild_id = str(message.guild.id)
                        # Replace language placeholders
                        import re
                        placeholders = re.findall(r'\{\{lang\.[^}]+\}\}', system_prompt)
                        for placeholder in placeholders:
                            key = placeholder.strip('{}').replace('{{lang.', '').replace('}}', '')
                            try:
                                translation = lang_manager.get(guild_id, key)
                                if translation:
                                    system_prompt = system_prompt.replace(placeholder, translation)
                            except Exception:
                                continue
                except Exception as exc:
                    asyncio.create_task(
                        func.report_error(exc, "Language replacement failed in message_agent prompt")
                    )
            
            return system_prompt
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Orchestrator._build_message_agent_prompt"))
            # Fall back to original get_system_prompt
            return get_system_prompt(str(bot_id), message)


    async def _sanitize_messages_for_model(self, messages: List[BaseMessage], model_name: str) -> List[BaseMessage]:
        """
        Sanitize messages for the specific model.
        - Ollama requires base64 images instead of direct HTTP URLs.
        - Gemini 3.x models require thought_signature for tool_calls. To prevent 400 errors, we convert past tool calls to text.
        """
        if "gemini-3" in model_name:
            from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
            sanitized = []
            for msg in messages:
                if isinstance(msg, ToolMessage):
                    tool_name = getattr(msg, "name", "unknown")
                    sanitized.append(HumanMessage(content=f"[System: Tool Result ({tool_name})]\n{msg.content}"))
                elif isinstance(msg, AIMessage):
                    has_tool_calls = bool(getattr(msg, "tool_calls", None))
                    has_function_call = "function_call" in msg.additional_kwargs or "tool_calls" in msg.additional_kwargs
                    
                    if has_tool_calls or has_function_call:
                        _text = msg.content if isinstance(msg.content, str) else ""
                        tool_names = []
                        if has_tool_calls:
                            tool_names = [tc.get("name", "unknown") for tc in getattr(msg, "tool_calls", [])]
                        if not _text.strip() and tool_names:
                            _text = f"[Assistant: Calling tool(s): {', '.join(tool_names)}]"
                        elif not _text.strip():
                            _text = "[Assistant: Internal process executed]"
                        # Create new AIMessage with clean kwargs to avoid triggering functionCall serialization
                        sanitized.append(AIMessage(content=_text))
                    else:
                        sanitized.append(msg)
                else:
                    sanitized.append(msg)
            return sanitized

        if not model_name.startswith("ollama:"):
            return messages

        import aiohttp
        import base64
        import copy
        
        sanitized = []
        
        async with aiohttp.ClientSession() as session:
            for msg in messages:
                if isinstance(msg.content, list):
                    new_content = []
                    for part in msg.content:
                        if isinstance(part, dict) and part.get("type") == "image_url":
                            url = part.get("image_url", {}).get("url", "")
                            if url.startswith("http"):
                                try:
                                    async with session.get(url) as resp:
                                        if resp.status == 200:
                                            img_data = await resp.read()
                                            b64_data = base64.b64encode(img_data).decode('utf-8')
                                            mime_type = resp.headers.get('Content-Type', 'image/jpeg')
                                            new_content.append({
                                                "type": "image_url",
                                                "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
                                            })
                                        else:
                                            new_content.append({"type": "text", "text": f"[Image attached: {url}]"})
                                except Exception as e:
                                    logger.warning(f"Failed to fetch image for Ollama: {e}")
                                    new_content.append({"type": "text", "text": f"[Image attached: {url}]"})
                            else:
                                new_content.append(part)
                        else:
                            new_content.append(part)
                    
                    new_msg = copy.copy(msg)
                    new_msg.content = new_content
                        
                    sanitized.append(new_msg)
                else:
                    sanitized.append(msg)
                    
        return sanitized

    async def handle_message(
        self, bot: Any, message_edit: Message, message: Message, logger: Any
    ) -> OrchestratorResponse:
        """
        Main entrypoint for handling an incoming Discord message.

        This method adapts to ContextManager returning a tuple:
        (procedural_context_str, short_term_msgs).

        short_term_msgs (List[BaseMessage]) are injected directly into the
        agents' messages lists (oldest -> newest), placed before the current
        user input to preserve conversation order.
        """
        # Default fallbacks
        procedural_context_str: str = ""
        short_term_msgs: List[BaseMessage] = []
        
        # Get LanguageManager
        lang_manager = bot.get_cog("LanguageManager")
        guild_id = str(message.guild.id) if message.guild else "0"

        # Provide feedback to the user that the bot is processing
        async with message.channel.typing():
            # Interrupt any active background memory tasks to prioritize this conversation
            if hasattr(bot, "message_tracker") and bot.message_tracker:
                bot.message_tracker.interrupt_all()
            
            # 1) Acquire contextual data from ContextManager with resilient error handling
            try:
                ctx = await self.context_manager.get_context(message)
                # Expect a tuple (procedural_str, short_term_msgs)
                if isinstance(ctx, tuple) and len(ctx) == 2:
                    procedural_context_str, short_term_msgs = ctx  # type: ignore
                else:
                    # unexpected return type; report and continue with fallbacks
                    asyncio.create_task(
                        func.report_error(
                            Exception(f"ContextManager.get_context returned unexpected type: {type(ctx)}"),
                            "Orchestrator.handle_message",
                        )
                    )
            except Exception as e:
                # Per design: report and continue with safe defaults
                asyncio.create_task(func.report_error(e, "ContextManager.get_context failed in Orchestrator"))
                procedural_context_str = ""
                short_term_msgs = []

            try:
                user = getattr(message, "author", None)
                if user is None:
                    raise ValueError("Discord message.author has no id")

                guild = getattr(message, "guild", None)
                if guild is None:
                    raise ValueError("Discord message.guild is None")

                runtime_context = OrchestratorRequest(bot=bot, message=message, logger=logger)
                
                # Get tools for info agent (excludes action tools)
                info_agent_tools = get_tools(user, guid=guild, runtime=runtime_context, agent_mode="info")
                
                # Get tools for message agent (only action tools)
                message_agent_tools = get_tools(user, guid=guild, runtime=runtime_context, agent_mode="message")
                
                # Also get full tool list for logging/response construction if needed
                # But OrchestratorResponse.tool_calls uses tool_list. 
                # We should probably combine them or just get all for that purpose.
                all_tools = info_agent_tools + message_agent_tools

                # --- Info agent setup with fallback ---
                # Note: Using manual fallback for consistency with message_agent
                # and to handle quota/rate limit errors more gracefully.
                
                try:
                    info_model_list = self.model_manager.get_model_priority_list("info_model")
                except Exception as e:
                    await func.report_error(e, "ModelManager.get_model_priority_list failed for info_model")
                    raise RuntimeError(f"Failed to get info_model priority list: {e}") from e

                info_system_prompt = self._build_info_agent_prompt(bot_id=bot.user.id, message=message)
                # IMPORTANT: Place static info_system_prompt before dynamic procedural_context_str to maximize KV cache reuse!
                full_info_prompt = f"{info_system_prompt}\n\n{procedural_context_str}"

                # Inject short-term memory messages directly before current user input
                messages_for_info_agent = list(short_term_msgs)
                
                # Update status to "Analyzing..."
                analyzing_msg = lang_manager.translate(guild_id, "system", "chat_bot", "responses", "analyzing") if lang_manager else "🔍 分析資訊中..."
                await safe_edit_message(message_edit, analyzing_msg)
                
                # Prepare callbacks
                callbacks = []
                if lang_manager:
                    callbacks.append(ToolFeedbackCallbackHandler(message_edit, lang_manager, guild_id))

                # Info agent fallback loop - try each model once, no retries
                # Use circuit breaker to skip models that recently failed
                circuit_breaker = get_model_circuit_breaker()
                info_result = None
                last_info_exception = None
                models_tried = 0
                
                for model_index, current_info_model in enumerate(info_model_list):
                    # Skip models that are in cooldown (recently failed)
                    if not circuit_breaker.is_available(current_info_model):
                        logger.info(f"Info agent: skipping model {current_info_model} (circuit breaker open)")
                        continue
                    
                    models_tried += 1
                    try:
                        logger.info(f"Info agent: trying model {current_info_model} ({model_index + 1}/{len(info_model_list)})")
                        
                        # Apply thought-budget control prompt for reasoning models
                        model_specific_prompt = full_info_prompt
                        if any(x in current_info_model.lower() for x in ["ollama", "deepseek", "gemma", "r1"]):
                            model_specific_prompt += llm_config.reasoning_optimization_prompt

                        # Instantiate model with zero retries to ensure immediate fallback on quota exhaustion
                        info_model_instance = init_chat_model(current_info_model, max_retries=0)
                        
                        info_agent = create_agent(
                            model=info_model_instance,
                            tools=info_agent_tools,
                            system_prompt=model_specific_prompt,
                            middleware=[DirectToolOutputMiddleware()],
                        )

                        sanitized_messages = await self._sanitize_messages_for_model(messages_for_info_agent, current_info_model)

                        # Execute info_agent to process user message and tools
                        info_result = await asyncio.wait_for(
                            info_agent.ainvoke(
                                {"messages": sanitized_messages},
                                config={"callbacks": callbacks}
                            ),
                            timeout=_LLM_CALL_TIMEOUT_SECONDS,
                        )
                        
                        # Success!
                        if models_tried > 1:
                            logger.info(f"Info agent fallback successful: used model {current_info_model}")
                        break
                        
                    except Exception as e:
                        last_info_exception = e
                        # Record failure in circuit breaker
                        category = circuit_breaker.record_failure(current_info_model, e)
                        logger.exception(f"Info agent model {current_info_model} failed (Category: {category.name}): {e}")
                        
                        # Briefly wait if transient to allow network/model state to stabilize
                        if category.name == "TRANSIENT":
                            await asyncio.sleep(0.5)
                        # Continue to next model immediately
                
                if info_result is None:
                    if last_info_exception is not None:
                        raise last_info_exception
                    else:
                        raise RuntimeError("All models skipped for info_agent due to circuit breaker cooldown.")
                
                # Extract the analysis output from info_agent result
                # Info agent should return analysis in a format suitable for message generation
                info_message: List[BaseMessage] = []
                if isinstance(info_result, dict) and "messages" in info_result:
                    info_message = info_result["messages"]
                else:
                    # Fallback: create a human message from the result
                    result_str = str(info_result) if info_result else ""
                    info_message = [HumanMessage(content=result_str)]
            except Exception as e:
                await asyncio.create_task(func.report_error(e, "info_agent failed"))
                raise

            try:
                # --- Message agent setup with streaming fallback ---
                # Note: ModelFallbackMiddleware doesn't support streaming mode,
                # so we implement fallback at the orchestrator level.

                try:
                    model_priority_list = self.model_manager.get_model_priority_list("message_model")
                except Exception as e:
                    await func.report_error(e, "ModelManager.get_model_priority_list failed for message_model")
                    raise RuntimeError(f"Failed to get message_model priority list: {e}") from e

                # Build message agent prompt using ProtectedPromptManager
                # This ensures system-level modules (Discord format, input parsing, etc.)  
                # are protected from user modification
                message_system_prompt = self._build_message_agent_prompt(bot.user.id, message)

                # IMPORTANT: Place static message_system_prompt before dynamic procedural_context_str to maximize KV cache reuse!
                full_message_prompt = f"{message_system_prompt}\n\n{procedural_context_str}"

                # Use the analysis from info_agent for message generation
                # Compose messages for message_agent with analysis output and context
                # Filter and transform ToolMessage and AIMessage with tool_calls.
                # Local models (e.g. Ollama) often don't support these specific message types/attributes,
                # so we convert them to plain text messages to preserve context without crashing.
                clean_info_messages: List[BaseMessage] = []
                for _msg in info_message:
                    if isinstance(_msg, ToolMessage):
                        # Convert ToolMessage to HumanMessage with English prefix and structured formatting
                        tool_name = getattr(_msg, "name", "unknown")
                        clean_info_messages.append(HumanMessage(content=f"[System: Tool Result ({tool_name})]\n{_msg.content}"))
                    elif isinstance(_msg, AIMessage) and _msg.tool_calls:
                        # Preserve text content; provide English placeholder if empty
                        _text = _msg.content if isinstance(_msg.content, str) else ""
                        if not _text.strip():
                            tool_names = ", ".join([tc.get("name", "unknown") for tc in _msg.tool_calls])
                            _text = f"[Assistant: Calling tool(s): {tool_names}]"
                        clean_info_messages.append(AIMessage(content=_text))
                    else:
                        clean_info_messages.append(_msg)
                messages_for_message_agent = clean_info_messages
                
                # Update status to "Thinking..."
                thinking_msg = lang_manager.translate(guild_id, "system", "chat_bot", "responses", "thinking") if lang_manager else "🧠 思考回覆中..."
                await safe_edit_message(message_edit, thinking_msg)
                
                # Streaming fallback loop - try each model once, no retries
                # Use circuit breaker to skip models that recently failed
                last_exception = None
                message_result = None
                models_tried = 0
                
                for model_index, current_model in enumerate(model_priority_list):
                    # Skip models that are in cooldown (recently failed)
                    if not circuit_breaker.is_available(current_model):
                        logger.info(f"Message agent: skipping model {current_model} (circuit breaker open)")
                        continue
                    
                    models_tried += 1
                    try:
                        logger.info(f"Message agent: trying model {current_model} ({model_index + 1}/{len(model_priority_list)})")
                        
                        # Apply thought-budget control prompt for reasoning models
                        model_specific_message_prompt = full_message_prompt
                        if any(x in current_model.lower() for x in ["ollama", "deepseek", "gemma", "r1"]):
                            model_specific_message_prompt += llm_config.reasoning_optimization_prompt

                        # Create agent with current model configured for zero retries
                        message_model_instance = init_chat_model(current_model, max_retries=0)
                        
                        message_agent = create_agent(
                            model=message_model_instance,
                            tools=message_agent_tools,
                            system_prompt=model_specific_message_prompt,
                            middleware=[ModelCallLimitMiddleware(run_limit=1, exit_behavior="end")],
                        )
                        
                        sanitized_messages = await self._sanitize_messages_for_model(messages_for_message_agent, current_model)
                        
                        streamer = message_agent.astream(
                            {"messages": sanitized_messages},
                            stream_mode="messages",
                        )
                        
                        # Check if there are more available models to try
                        remaining_models = [m for m in model_priority_list[model_index + 1:] if circuit_breaker.is_available(m)]
                        is_last_available = len(remaining_models) == 0
                        
                        message_result = await asyncio.wait_for(
                            send_message(
                                bot,
                                message_edit,
                                message,
                                streamer,
                                raise_exception=not is_last_available,
                                tools=all_tools
                            ),
                            timeout=_LLM_CALL_TIMEOUT_SECONDS,
                        )
                        
                        # Success!
                        if models_tried > 1:
                            logger.info(f"Fallback successful: used model {current_model}")
                        break
                        
                    except Exception as e:
                        last_exception = e
                        # Record failure in circuit breaker
                        category = circuit_breaker.record_failure(current_model, e)
                        logger.exception(f"Model {current_model} failed (Category: {category.name}): {e}")
                        
                        # Briefly wait if transient to allow network/model state to stabilize
                        if category.name == "TRANSIENT":
                            await asyncio.sleep(0.5)
                        # Continue to next model immediately
                    
                    # If we got a result, break out of the model loop
                    if message_result is not None:
                        break
                
                # If all models failed, raise the last exception
                if message_result is None:
                    if last_exception is not None:
                        raise last_exception
                    else:
                        raise RuntimeError("All models skipped due to circuit breaker cooldown.")

            except Exception as e:
                await asyncio.create_task(func.report_error(e, "message_agent failed"))
                raise

            resp = OrchestratorResponse.construct()
            resp.reply = message_result
            
            # Build concise tool list for logging (only names, not full schemas)
            tool_names = [getattr(t, "name", repr(t)) for t in all_tools]
            
            # Store full tool info in response if needed
            resp.tool_calls = [
                {"tool": getattr(t, "name", repr(t)), "args": getattr(t, "args", None)} for t in all_tools
            ]
            
            # Log with concise tool names only
            logger.info(f"{bot.user.name}:{resp.reply}, available_tools: {tool_names}")
            return resp


__all__ = ["Orchestrator"]