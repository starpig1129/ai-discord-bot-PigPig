"""Context manager for assembling SystemContext from memory providers."""

import asyncio
import discord
from typing import Optional

from llm.memory.schema import SystemContext
from llm.memory.short_term import ShortTermMemoryProvider
from llm.memory.episodic import EpisodicMemoryProvider
from llm.memory.procedural import ProceduralMemoryProvider


class ContextManager:
    """
    The central coordinator for gathering context from various memory sources.
    """

    def __init__(
        self,
        short_term_provider: ShortTermMemoryProvider,
        episodic_provider: EpisodicMemoryProvider,
        procedural_provider: ProceduralMemoryProvider,
    ):
        """
        Initializes the ContextManager with all required memory providers.

        Args:
            short_term_provider: Provider for recent message history.
            episodic_provider: Provider for vector store search.
            procedural_provider: Provider for user background data.
        """
        self.short_term_provider = short_term_provider
        self.episodic_provider = episodic_provider
        self.procedural_provider = procedural_provider

    async def build_context(self, message: discord.Message) -> SystemContext:
        """
        Builds the full system context by gathering information from all providers.

        This method runs all providers concurrently to improve performance.

        Args:
            message: The current discord.Message object.

        Returns:
            A SystemContext object containing all gathered information.
        """
        # Run all providers concurrently
        short_term_task = self.short_term_provider.get(message)
        episodic_task = self.episodic_provider.get(message)
        procedural_task = self.procedural_provider.get(message)

        short_term_memory, episodic_memory, procedural_memory = await asyncio.gather(
            short_term_task,
            episodic_task,
            procedural_task,
        )

        # Assemble the final context object
        system_context = SystemContext(
            short_term_memory=short_term_memory,
            episodic_memory=episodic_memory,
            procedural_memory=procedural_memory,
            current_channel_name=message.channel.name,
        )

        return system_context