"""
EventSummarizationService: Process Discord message lists into meaningful events using LLM summarization.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, cast, TypeVar, Type
from datetime import timezone

import discord
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from function import func
from addons.settings import MemoryConfig, prompt_config
from addons.logging import get_logger
from llm.model_manager import ModelManager
from llm.model_circuit_breaker import get_model_circuit_breaker

log = get_logger(__name__)

T = TypeVar('T', bound=BaseModel)


@dataclass
class EventMetadata:
    """Structured metadata for an event."""
    start_message_id: int
    end_message_id: int
    channel_id: int
    guild_id: int
    user_ids: List[int]
    start_timestamp: float
    end_timestamp: float
    reaction_list: List[Dict[str, Any]]
    event_type: Optional[str] = None


class Entity(BaseModel):
    """Represents an entity extracted from the conversation."""
    name: str = Field(..., description="The name of the entity (person, place, organization, concept, etc.).")
    type: str = Field(..., description="The type of the entity (e.g., Person, Location, Organization, Topic).")
    description: str = Field(..., description="A brief description of the entity based on the conversation context.")

class MemoryFragment(BaseModel):
    """Represents a single, distinct memory extracted from a conversation.

    Attributes:
        query_key: A concise, objective, and human-readable summary of a specific
            event, decision, or piece of information from the conversation.
        query_keywords: A list of machine-optimized keywords for efficient
            database searching and retrieval.
        query_value: The detailed content of the memory, suitable for being
            returned as a search result.
        start_message_id: The ID of the first message in the conversation that
            is part of this memory.
        end_message_id: The ID of the last message in the conversation that is
            part of this memory.
    """
    query_key: str = Field(
        ...,
        description=(
            "A concise, objective, and human-readable summary of a specific event, "
            "decision, or piece of information from the conversation."
        ),
    )
    query_keywords: List[str] = Field(
        ...,
        description="A list of machine-optimized keywords for efficient database searching and retrieval.",
    )
    query_value: str = Field(
        ...,
        description="The detailed content of the memory, suitable for being returned as a search result.",
    )
    start_message_id: int = Field(
        ...,
        description="The ID of the first message in the conversation that is part of this memory. This corresponds to the 'id' field in the provided conversation history (e.g., 1, 2, 3).",
    )
    end_message_id: int = Field(
        ...,
        description="The ID of the last message in the conversation that is part of this memory. This corresponds to the 'id' field in the provided conversation history (e.g., 1, 2, 3).",
    )
    entities: List[Entity] = Field(
        default_factory=list,
        description="A list of entities (people, places, concepts) identified in this memory fragment.",
    )

class MemoryFragmentList(BaseModel):
    """A list of MemoryFragment objects, representing all significant events extracted from a conversation.

    Attributes:
        fragments: A list of memory fragments extracted from the conversation.
    """
    fragments: List[MemoryFragment] = Field(
        ...,
        description="A list of memory fragments extracted from the conversation.",
    )
@dataclass
class EventSummary:
    """Structured output for an event summary."""
    query_key: str
    query_keywords: List[str]
    query_value: str
    entities: List[Dict[str, str]]
    metadata: EventMetadata


class EventSummarizationService:
    """
    Service for processing Discord messages into meaningful event summaries using LLM.
    
    This service groups related messages and uses LLM to extract key information
    for improved memory retrieval and vectorization.
    """

    def __init__(self, bot: discord.Client, settings: MemoryConfig) -> None:
        """
        Initialize the Event Summarization Service.
        
        Args:
            bot: Discord bot instance
            settings: Memory configuration settings
        """
        self.bot = bot
        self.settings = settings
        self.model_manager = ModelManager()

    def _extract_structured_response(
        self,
        response: Any,
        expected_model: Type[T],
        context: str
    ) -> Optional[T]:
        """
        Unified extractor for structured agent responses.
        
        Args:
            response: Raw response returned by agent.ainvoke()
            expected_model: Expected Pydantic model class
            context: Logging context
            
        Returns:
            Parsed model instance on success, None on failure.
        """
        try:
            # Step 1: Extract payload from response
            payload = None
            if isinstance(response, dict):
                # Priority order: structured_response > output > result > entire response
                payload = (
                    response.get("structured_response") or
                    response.get("output") or
                    response.get("result") or
                    response
                )
            else:
                payload = response
            
            # Step 2: Check if payload is already the correct type
            if isinstance(payload, expected_model):
                log.debug(f"{context}: Payload already correct type")
                return payload
            
            # Step 3: Convert based on payload type
            if isinstance(payload, str):
                # JSON string
                result = expected_model.model_validate_json(payload)
                log.debug(f"{context}: Parsed from JSON string")
                return result
            elif isinstance(payload, dict):
                # Dictionary
                result = expected_model.model_validate(payload)
                log.debug(f"{context}: Parsed from dict")
                return result
            elif hasattr(payload, "model_dump"):
                # Pydantic v2 model
                result = expected_model.model_validate(payload.model_dump())
                log.debug(f"{context}: Parsed from Pydantic v2 model")
                return result
            elif hasattr(payload, "dict"):
                # Pydantic v1 model
                result = expected_model.model_validate(payload.dict())
                log.debug(f"{context}: Parsed from Pydantic v1 model")
                return result
            else:
                raise ValueError(f"Unsupported payload type: {type(payload)}")
                
        except Exception as e:
            log.error(
                f"{context}: Failed to extract {expected_model.__name__}: {e}",
                exc_info=True
            )
            try:
                asyncio.create_task(func.report_error(
                    e,
                    f"event_summarization.extract_structured_response_failed "
                    f"context={context} model={expected_model.__name__}"
                ))
            except Exception:
                log.exception("func.report_error failed")
            return None

    async def summarize_events(self, messages: List[discord.Message], previous_summary: str = "") -> List[EventSummary]:
        """
        Process a list of messages and extract event summaries using LLM.
        
        Args:
            messages: List of Discord messages to process
            previous_summary: Summary of previous events for context
            
        Returns:
            List of EventSummary objects representing extracted events
        """
        if not messages:
            return []

        try:
            # Group messages into events (initial implementation treats all as single event)
            grouped_messages = await self._group_messages(messages)
            
            # Process each group into event summaries
            event_summaries = []
            for message_group in grouped_messages:
                summary_list = await self._process_message_group(message_group, previous_summary)
                if summary_list:
                    event_summaries.extend(summary_list)
            
            return event_summaries
            
        except Exception as e:
            log.error(f"Error in summarize_events: {e}", exc_info=True)
            await func.report_error(e, "EventSummarizationService/summarize_events")
            return []

    async def _group_messages(self, messages: List[discord.Message]) -> List[List[discord.Message]]:
        """
        Group related messages into events.
        
        Current implementation: treat all messages as a single event.
        Future implementation: implement sophisticated grouping algorithms.
        
        Args:
            messages: List of Discord messages
            
        Returns:
            List of message groups, each group is a list of messages
        """
        # For now, treat all messages as a single event
        # This provides a foundation for future sophisticated grouping algorithms
        log.debug(f"Grouping {len(messages)} messages as single event (initial implementation)")
        return [messages]

    async def _process_message_group(self, messages: List[discord.Message], previous_summary: str = "") -> Optional[List[EventSummary]]:
        """
        Process a group of messages into an event summary using LLM.
        
        Args:
            messages: Group of related Discord messages
            previous_summary: Context from previous events
            
        Returns:
            EventSummary object or None if processing failed
        """
        if not messages:
            return None

        try:
            memory_list = []
            # Prepare message data for LLM processing
            message_data = await self._prepare_message_data(messages)
            
            # Get LLM response using the episodic memory extractor
            llm_response = await self._get_llm_summary(message_data, previous_summary)
            
            if not llm_response:
                log.warning("No LLM response received for message group")
                return None
            for fragment in llm_response.fragments:
                # Create EventSummary from LLM response and message metadata
                event_summary = await self._create_event_summary(messages, fragment)
                if event_summary:
                    memory_list.append(event_summary)

            return memory_list
            
        except Exception as e:
            log.error(f"Error processing message group: {e}", exc_info=True)
            await func.report_error(e, "EventSummarizationService/_process_message_group")
            return None

    async def _prepare_message_data(self, messages: List[discord.Message]) -> List[Dict[str, Any]]:
        """
        Prepare message data for LLM processing.
        
        Args:
            messages: List of Discord messages
            
        Returns:
            List of message dictionaries with author, timestamp, and content
        """
        message_data = []
        
        for index, message in enumerate(messages, start=1):
            # Format timestamp as ISO string for LLM processing
            timestamp = message.created_at.replace(tzinfo=timezone.utc).isoformat()
            
            message_dict = {
                "id": index,
                "author": message.author.display_name or message.author.name,
                "content": message.content or ""  # Handle empty content
            }
            message_data.append(message_dict)
        
        return message_data

    async def _get_llm_summary(self, message_data: List[Dict[str, Any]], previous_summary: str = "") -> Optional[MemoryFragmentList]:
        """
        Get event summary from LLM using the episodic memory extractor prompt with structured output.
        
        Uses circuit breaker to avoid calling models that are known to be failing.
        
        Args:
            message_data: Prepared message data for LLM processing
            previous_summary: Context from previous events
            
        Returns:
            MemoryFragmentList object or None if failed
        """
        try:
            # Get model priority list for fallback
            try:
                model_priority_list = self.model_manager.get_model_priority_list("episodic_memory_model")
                log.debug(f"Episodic memory model priority list: {model_priority_list}")
            except ValueError as e:
                log.error(f"Failed to get model list for episodic_memory_model: {e}")
                return None
            
            # Prepare the system and user prompts
            system_prompt = self._get_system_prompt()
            user_prompt = self._get_user_prompt_with_messages(message_data, previous_summary)
            
            # Prepare the message list
            message_list = [HumanMessage(content=user_prompt)]
            
            # Use circuit breaker to skip known-failing models
            circuit_breaker = get_model_circuit_breaker()
            last_exception = None
            
            for model_index, current_model in enumerate(model_priority_list):
                # Skip models that are in cooldown (recently failed)
                if not circuit_breaker.is_available(current_model):
                    log.info(f"Episodic memory: skipping model {current_model} (circuit breaker open)")
                    continue
                
                try:
                    log.debug(f"Episodic memory: trying model {current_model} ({model_index + 1}/{len(model_priority_list)})")
                    
                    # Create the agent with structured output
                    agent = create_agent(
                        current_model,
                        tools=[],
                        system_prompt=system_prompt,
                        response_format=MemoryFragmentList,  # Use structured output
                        middleware=[]
                    )
                    
                    # Make the API call to the LLM
                    response = await agent.ainvoke(cast(Any, {"messages": message_list}))
                    
                    # Extract structured response using the unified method
                    memory_fragment = self._extract_structured_response(
                        response,
                        MemoryFragmentList,
                        "Episodic Memory Extractor"
                    )
                    
                    if memory_fragment:
                        # Log a concise preview
                        try:
                            first_preview = (
                                memory_fragment.fragments[0].query_value[:50]
                                if getattr(memory_fragment, "fragments", None)
                                and len(memory_fragment.fragments) > 0
                                else ""
                            )
                            log.debug(
                                f"Successfully extracted {len(memory_fragment.fragments)} memory fragment(s); preview: {first_preview}..."
                            )
                        except Exception:
                            log.debug(
                                "Successfully extracted memory fragment(s); unable to generate preview"
                            )
                        return memory_fragment
                    else:
                        raise ValueError("Failed to extract memory fragment from LLM response")
                        
                except Exception as e:
                    last_exception = e
                    # Record failure in circuit breaker
                    circuit_breaker.record_failure(current_model, e)
                    log.warning(f"Episodic memory model {current_model} failed: {e}")
                    # Continue to next model
            
            # All models failed
            log.warning("Failed to extract memory fragment from LLM response after all models attempted")
            if last_exception:
                await func.report_error(last_exception, "EventSummarizationService/_get_llm_summary - all models failed")
            return None
            
        except Exception as e:
            log.error(f"Error getting LLM summary: {e}", exc_info=True)
            await func.report_error(e, "EventSummarizationService/_get_llm_summary")
            return None

    def _get_system_prompt(self) -> str:
        """Get the system prompt from the episodic memory extractor template."""
        try:
            return prompt_config.get_system_prompt("episodic_memory_agent")
        except Exception as e:
            asyncio.create_task(func.report_error(e, "EventSummarizationService/_get_system_prompt"))
            # Fallback system prompt
            return (
                    "You are an AI expert specializing in analyzing conversation histories "
                    "to extract key facts, events, and statements as structured memory fragments. "
                    "Your purpose is to create a concise, machine-readable, and human-readable "
                    "record of significant moments from a dialogue."
                )

    def _get_user_prompt_with_messages(self, message_data: List[Dict[str, Any]], previous_summary: str = "") -> str:
        """
        Get the user prompt with the prepared message data.
        
        Args:
            message_data: Prepared message data
            previous_summary: Context from previous events
            
        Returns:
            User prompt string with message data
        """
        try:
            messages_text = json.dumps(message_data, ensure_ascii=False, indent=2)
            
            context_text = ""
            if previous_summary:
                context_text = f"Previous Context:\n{previous_summary}\n\n"
                
            return (
                f"{context_text}"
                f"Process the following conversation history:\n\n{messages_text}\n\n"
            )
        except Exception as e:
            log.error(f"Error getting user prompt: {e}", exc_info=True)
            # Return basic prompt with messages
            messages_text = json.dumps(message_data, ensure_ascii=False, indent=2)
            return f"Process this conversation:\n{messages_text}"

    async def _create_event_summary(
        self,
        messages: List[discord.Message],
        memory_fragment: MemoryFragment
    ) -> Optional[EventSummary]:
        """
        Create an EventSummary from LLM response and message metadata.
        
        Args:
            messages: Original message group
            memory_fragment: Structured response from LLM
            
        Returns:
            EventSummary object or None if creation failed
        """
        try:
            # Extract data from the structured response
            query_key = memory_fragment.query_key
            
            query_keywords = memory_fragment.query_keywords
            
            # Use query_value from structured response
            query_value = memory_fragment.query_value
            
            # Create metadata from message group
            metadata = self._create_event_metadata(messages,memory_fragment)
            
            # Extract entities
            entities = []
            if hasattr(memory_fragment, 'entities'):
                for entity in memory_fragment.entities:
                    entities.append({
                        "name": entity.name,
                        "type": entity.type,
                        "description": entity.description
                    })
            
            return EventSummary(
                query_key=query_key,
                query_keywords=query_keywords,
                query_value=query_value,
                entities=entities,
                metadata=metadata
            )
            
        except Exception as e:
            log.error(f"Error creating event summary: {e}", exc_info=True)
            await func.report_error(e, "EventSummarizationService/_create_event_summary")
            return None

    def _generate_query_value(self, summary: str, query_key: str) -> str:
        """
        Generate query value for vector search.
        
        Args:
            summary: Event summary
            query_key: Query key
            
        Returns:
            Generated query value
        """
        try:
            # Combine summary and query_key for a comprehensive search value
            combined_text = f"{summary} {query_key}".strip()
            
            # Remove extra whitespace and ensure reasonable length
            query_value = " ".join(combined_text.split())[:500]  # Limit length
            
            return query_value
            
        except Exception as e:
            log.error(f"Error generating query value: {e}", exc_info=True)
            return query_key if query_key else summary

    def _create_event_metadata(self, messages: List[discord.Message], memory_fragment: MemoryFragment) -> EventMetadata:
        """
        Create event metadata from a group of messages using MemoryFragment info.
        
        Args:
            messages: List of Discord messages
            memory_fragment: MemoryFragment containing start_message_id and end_message_id
            
        Returns:
            EventMetadata object
        """
        try:
            # Use message IDs from memory_fragment (these are 1-based indices)
            start_seq_id = memory_fragment.start_message_id
            end_seq_id = memory_fragment.end_message_id
            
            # Map sequence IDs back to real messages
            # Note: sequence IDs are 1-based, so we subtract 1 for list index
            start_message = None
            end_message = None
            
            if 0 < start_seq_id <= len(messages):
                start_message = messages[start_seq_id - 1]
            
            if 0 < end_seq_id <= len(messages):
                end_message = messages[end_seq_id - 1]
            
            # If we couldn't find the exact messages by index, fallback to first and last
            if not start_message:
                start_message = messages[0] if messages else None
            if not end_message:
                end_message = messages[-1] if messages else None
                
            # Ensure start comes before end
            if start_message and end_message and messages.index(start_message) > messages.index(end_message):
                start_message, end_message = end_message, start_message

            # Get the real Discord IDs
            start_message_id = start_message.id if start_message else 0
            end_message_id = end_message.id if end_message else 0
            
            # Collect messages in range
            messages_in_range = []
            if start_message and end_message:
                try:
                    start_idx = messages.index(start_message)
                    end_idx = messages.index(end_message)
                    messages_in_range = messages[start_idx : end_idx + 1]
                except ValueError:
                    # Fallback if messages not found in list (shouldn't happen with indices)
                    messages_in_range = messages
            
            # Collect unique user IDs from messages within the range
            user_ids = list(set(msg.author.id for msg in messages_in_range))
            
            # Collect reaction data from messages within the range
            reaction_list = []
            for message in messages_in_range:
                for reaction in message.reactions:
                    reaction_dict = {
                        "emoji": str(reaction.emoji),
                        "count": reaction.count,
                        "message_id": message.id
                    }
                    reaction_list.append(reaction_dict)
            
            # Get channel and guild info from start message
            channel_id = start_message.channel.id
            guild_id = start_message.guild.id if start_message.guild else 0
            
            return EventMetadata(
                start_message_id=start_message_id,
                end_message_id=end_message_id,
                channel_id=channel_id,
                guild_id=guild_id,
                user_ids=user_ids,
                start_timestamp=start_message.created_at.timestamp(),
                end_timestamp=end_message.created_at.timestamp(),
                reaction_list=reaction_list,
                event_type="conversation"  # Default event type
            )
            
        except Exception as e:
            log.error(f"Error creating event metadata: {e}", exc_info=True)
            # Return minimal metadata as fallback
            message = messages[0] if messages else None
            return EventMetadata(
                start_message_id=memory_fragment.start_message_id if memory_fragment else (message.id if message else 0),
                end_message_id=memory_fragment.end_message_id if memory_fragment else (message.id if message else 0),
                channel_id=message.channel.id if message and hasattr(message, 'channel') else 0,
                guild_id=message.guild.id if message and hasattr(message, 'guild') and message.guild else 0,
                user_ids=[message.author.id] if message else [],
                start_timestamp=message.created_at.timestamp() if message else 0.0,
                end_timestamp=message.created_at.timestamp() if message else 0.0,
                reaction_list=[],
                event_type="conversation"
            )