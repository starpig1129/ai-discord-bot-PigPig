from __future__ import annotations
import asyncio
from typing import Any, List
import re

from discord import Message
from langchain_core.messages import BaseMessage
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, AgentMiddleware, hook_config

from llm.model_manager import ModelManager
from llm.tools_factory import get_tools
from llm.schema import OrchestratorResponse, OrchestratorRequest
from llm.utils.send_message import send_message, safe_edit_message
from function import func
from addons.settings import prompt_config
from .prompting.system_prompt import get_system_prompt
from .prompting.protected_prompt_manager import get_protected_prompt_manager

from llm.context_manager import ContextManager
from llm.memory.short_term import ShortTermMemoryProvider
from llm.memory.procedural import ProceduralMemoryProvider
from llm.callbacks import ToolFeedbackCallbackHandler


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

        if user_manager is None:
            asyncio.create_task(
                func.report_error(
                    Exception("Missing user_manager on bot UserDataCog for Orchestrator"),
                    "Orchestrator.__init__",
                )
            )

        short_term_provider = ShortTermMemoryProvider(bot=bot, limit=15)
        procedural_provider = ProceduralMemoryProvider(user_manager=user_manager)

        self.context_manager = ContextManager(
            short_term_provider=short_term_provider,
            procedural_provider=procedural_provider,
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

                # --- Info agent setup ---
                try:
                    info_model, fallback = self.model_manager.get_model("info_model")
                except Exception as e:
                    await func.report_error(e, "ModelManager.get_model failed for info_model")
                    raise RuntimeError(f"Failed to get info_model: {e}") from e

                info_system_prompt = self._build_info_agent_prompt(bot_id=bot.user.id, message=message)
                # IMPORTANT: full_info_prompt should only include procedural_context_str (string) and system prompt.
                full_info_prompt = f"{procedural_context_str}\n\n{info_system_prompt}"
                #print("Info Agent Prompt:\n", full_info_prompt)

                info_agent = create_agent(
                    model=info_model,
                    tools=info_agent_tools,
                    system_prompt=full_info_prompt,
                    middleware=[fallback,DirectToolOutputMiddleware()],
                )

                # Inject short-term memory messages directly before current user input
                messages_for_info_agent = list(short_term_msgs)
                #print("Info Agent Messages:\n", messages_for_info_agent)
                
                # Update status to "Analyzing..."
                analyzing_msg = lang_manager.translate(guild_id, "system", "chat_bot", "responses", "analyzing") if lang_manager else "🔍 分析資訊中..."
                await safe_edit_message(message_edit, analyzing_msg)
                
                # Prepare callbacks
                callbacks = []
                if lang_manager:
                    callbacks.append(ToolFeedbackCallbackHandler(message_edit, lang_manager, guild_id))

                # Execute info_agent to process user message and tools
                info_result = await info_agent.ainvoke(
                    {"messages": messages_for_info_agent},
                    config={"callbacks": callbacks}
                )
                
                # Extract the analysis output from info_agent result
                # Info agent should return analysis in a format suitable for message generation
                info_message: List[BaseMessage] = []
                if isinstance(info_result, dict) and "messages" in info_result:
                    info_message = info_result["messages"]
                else:
                    # Fallback: create a human message from the result
                    result_str = str(info_result) if info_result else ""
                    from langchain_core.messages import HumanMessage
                    info_message = [HumanMessage(content=result_str)]
            except Exception as e:
                await asyncio.create_task(func.report_error(e, "info_agent failed"))
                raise

            try:
                # --- Message agent setup ---

                try:
                    message_model, fallback = self.model_manager.get_model("message_model")
                except Exception as e:
                    await func.report_error(e, "ModelManager.get_model failed for message_model")
                    raise RuntimeError(f"Failed to get message_model: {e}") from e

                # Build message agent prompt using ProtectedPromptManager
                # This ensures system-level modules (Discord format, input parsing, etc.)  
                # are protected from user modification
                message_system_prompt = self._build_message_agent_prompt(bot.user.id, message)

                # full_message_prompt must only include procedural_context_str and system prompt
                full_message_prompt = f"{procedural_context_str}\n\n{message_system_prompt}"
                #print("Message Agent Prompt:\n", full_message_prompt)
                message_agent = create_agent(
                    model=message_model,
                    tools=message_agent_tools,
                    system_prompt=full_message_prompt,
                    middleware=[fallback, ModelCallLimitMiddleware(run_limit=1, exit_behavior="end")],
                )

                # Use the analysis from info_agent for message generation
                # Compose messages for message_agent with analysis output and context
                messages_for_message_agent = list(info_message)

                #print("Message Agent Messages:\n", messages_for_message_agent)
                
                # Update status to "Thinking..."
                thinking_msg = lang_manager.translate(guild_id, "system", "chat_bot", "responses", "thinking") if lang_manager else "🧠 思考回覆中..."
                await safe_edit_message(message_edit, thinking_msg)
                
                # Retry loop for message generation to handle empty responses or transient errors
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        streamer = message_agent.astream(
                            {"messages": messages_for_message_agent},
                            stream_mode="messages",
                        )
                        
                        # On last attempt, let send_message handle the error (send error msg to user)
                        # For earlier attempts, raise exception to trigger retry
                        should_raise = (attempt < max_retries - 1)
                        
                        message_result = await send_message(
                            bot, 
                            message_edit, 
                            message, 
                            streamer,
                            raise_exception=should_raise,
                            tools=all_tools
                        )
                        # If we get here, success!
                        break
                        
                    except Exception as e:
                        logger.warning(f"Message generation attempt {attempt + 1}/{max_retries} failed: {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)  # Wait a bit before retry
                        else:
                            # This block should theoretically not be reached if raise_exception=False 
                            # on the last attempt, as send_message would return the error string.
                            # But if it does raise (e.g. critical error), re-raise it.
                            raise

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