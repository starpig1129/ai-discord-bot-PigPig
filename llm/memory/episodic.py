"""Episodic memory provider module."""

from typing import Optional

import discord

from llm.memory.schema import EpisodicMemory
from cogs.memory.interfaces.vector_store_interface import VectorStoreInterface


class EpisodicMemoryProvider:
    """
    Provides episodic memory by searching for relevant memory fragments
    in a vector store.
    """

    def __init__(self, vector_store: VectorStoreInterface):
        """
        Initializes the provider with a vector store interface.

        Args:
            vector_store (VectorStoreInterface): An instance of a class that
                implements the vector store interface.
        """
        self.vector_store = vector_store

    async def get(
        self,
        message: discord.Message,
        vector_query: Optional[str] = None,
        keyword_query: Optional[str] = None
    ) -> EpisodicMemory:
        """
        Searches the vector store for memories related to the query.

        Args:
            message (discord.Message): The current message object.
            vector_query (Optional[str]): The query text for vector-based search.
            keyword_query (Optional[str]): The query text for keyword-based search.

        Returns:
            EpisodicMemory: An object containing the list of found memory fragments.
        """
        if not vector_query and not keyword_query:
            # Use message content as default query if none is provided
            vector_query = message.content

        user_id = str(message.author.id)

        fragments = await self.vector_store.search(
            vector_query=vector_query,
            keyword_query=keyword_query,
            user_id=user_id
        )

        return EpisodicMemory(fragments=fragments)