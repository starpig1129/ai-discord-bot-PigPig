# coding: utf-8
"""
Qdrant-based Vector Store using LangChain integration.
Simplified implementation using langchain-qdrant package.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from addons.settings import MemoryConfig
from addons.tokens import tokens
from cogs.memory.exceptions import VectorOperationError, SearchError
from cogs.memory.interfaces.vector_store_interface import MemoryFragment, VectorStoreInterface

logger = logging.getLogger(__name__)


class QdrantStore(VectorStoreInterface):
    """LangChain Qdrant vector store wrapper."""

    def __init__(self, settings: MemoryConfig, embedding_model: Optional[Embeddings]) -> None:
        if not embedding_model:
            raise VectorOperationError("Embedding model is required")

        qdrant_url = getattr(settings, "qdrant_url", None)
        collection_name = getattr(settings, "qdrant_collection_name", None)
        embedding_dim = getattr(settings, "embedding_dim", None)
        api_key = getattr(tokens, "vector_store_api_key", None)

        if not qdrant_url or not collection_name or not embedding_dim:
            raise VectorOperationError("Missing required Qdrant settings")

        self.settings = settings
        self.embedding_model = embedding_model
        self.collection_name = collection_name
        self.embedding_dim = int(embedding_dim)

        try:
            self.client = QdrantClient(url=qdrant_url, api_key=api_key, timeout=60)
            # Log basic connection info (do not log api_key)
            logger.debug(
                "Qdrant client initialized (url=%s, collection=%s, embedding_dim=%d)",
                qdrant_url,
                self.collection_name,
                self.embedding_dim,
            )

            try:
                exists = self.client.collection_exists(self.collection_name)
                logger.debug("Qdrant collection exists=%s for %s", exists, self.collection_name)
                if not exists:
                    logger.info("Creating Qdrant collection: %s", self.collection_name)
                    self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(
                            size=self.embedding_dim,
                            distance=Distance.COSINE
                        ),
                    )
                    logger.info("Created Qdrant collection: %s", self.collection_name)
            except Exception as e:
                logger.exception("Failed while ensuring Qdrant collection exists")
                asyncio.create_task(self._report_error(e))
                raise VectorOperationError("Failed to ensure Qdrant collection") from e

            # Initialize LangChain QdrantVectorStore
            self.vector_store = QdrantVectorStore(
                client=self.client,
                collection_name=self.collection_name,
                embedding=self.embedding_model,
            )
        except Exception as e:
            asyncio.create_task(self._report_error(e))
            raise VectorOperationError("Failed to initialize Qdrant") from e

    async def ensure_storage(self) -> None:
        """Ensure payload indexes exist.

        Collection creation is handled in __init__ to avoid langchain-qdrant
        raising 404 when the collection is missing during QdrantVectorStore init.
        """
        try:
            # Ensure collection exists before creating indexes; if not, log and return.
            if not self.client.collection_exists(self.collection_name):
                logger.warning(
                    "ensure_storage: collection %s does not exist; skipping index creation",
                    self.collection_name,
                )
                return

            # Create payload indexes for filtering (idempotent)
            from qdrant_client.models import PayloadSchemaType

            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="author_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="channel_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                logger.debug("Payload indexes may already exist for collection %s", self.collection_name)
        except Exception as e:
            asyncio.create_task(self._report_error(e))
            raise VectorOperationError("Failed to ensure storage") from e

    async def add_memories(self, memories: List[MemoryFragment]) -> None:
        """Add memories using LangChain's add_documents."""
        if not memories:
            return

        try:
            # Convert MemoryFragments to LangChain Documents
            documents = []
            for mem in memories:
                metadata = getattr(mem, "metadata", {}) or {}
                if isinstance(metadata, dict):
                    # Ensure IDs are strings for filtering
                    if "author_id" in metadata:
                        metadata["author_id"] = str(metadata["author_id"])
                    if "channel_id" in metadata:
                        metadata["channel_id"] = str(metadata["channel_id"])
                
                doc = Document(
                    page_content=mem.query_key,  # Embed query_key
                    metadata={
                        "summary": mem.content,
                        "fragment_id": getattr(mem, "id", ""),
                        **metadata
                    }
                )
                documents.append(doc)

            # Use LangChain's batch add
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.vector_store.add_documents(documents)
            )

        except Exception as e:
            asyncio.create_task(self._report_error(e))
            raise VectorOperationError("Failed to add memories") from e

    async def search_memories_by_vector(
        self,
        query_text: str,
        limit: int = 8,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> List[MemoryFragment]:
        """Vector similarity search with metadata filtering."""
        try:
            # Build filter dict for LangChain
            search_filter = {}
            if user_id:
                search_filter["author_id"] = str(user_id)
            if channel_id:
                search_filter["channel_id"] = str(channel_id)

            # Use LangChain's similarity_search
            loop = asyncio.get_event_loop()
            docs = await loop.run_in_executor(
                None,
                lambda: self.vector_store.similarity_search(
                    query_text,
                    k=limit,
                    filter=search_filter if search_filter else None
                )
            )

            # Convert back to MemoryFragments
            results = []
            for doc in docs:
                metadata = doc.metadata.copy()
                summary = metadata.pop("summary", doc.page_content)
                
                mem = MemoryFragment(
                    id=metadata.get("fragment_id", ""),
                    content=summary,
                    metadata=metadata,
                    query_key=doc.page_content,
                    score=None  # LangChain doesn't return scores by default
                )
                results.append(mem)

            return results

        except Exception as e:
            asyncio.create_task(self._report_error(e))
            raise SearchError("Vector search failed") from e

    async def search_memories_by_keyword(
        self,
        query_text: str,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        k: int = 5
    ) -> List[MemoryFragment]:
        """Keyword search using Qdrant scroll API."""
        # Keep your existing implementation or use vector search as fallback
        return await self.search_memories_by_vector(
            query_text, limit=k, user_id=user_id, channel_id=channel_id
        )

    async def search(
        self,
        vector_query: Optional[str] = None,
        keyword_query: Optional[str] = None,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> List[MemoryFragment]:
        """Hybrid search combining vector and keyword results."""
        if not vector_query and not keyword_query:
            raise ValueError("At least one query type required")

        vector_k = getattr(self.settings, "vector_search_k", 5)
        keyword_k = getattr(self.settings, "keyword_search_k", 3)

        if vector_query and not keyword_query:
            return await self.search_memories_by_vector(
                vector_query, limit=vector_k, user_id=user_id, channel_id=channel_id
            )

        if keyword_query and not vector_query:
            return await self.search_memories_by_keyword(
                keyword_query, user_id=user_id, channel_id=channel_id, k=keyword_k
            )

        # Both queries: run in parallel and merge
        vec_task = self.search_memories_by_vector(
            vector_query, limit=vector_k, user_id=user_id, channel_id=channel_id
        )
        kw_task = self.search_memories_by_keyword(
            keyword_query, user_id=user_id, channel_id=channel_id, k=keyword_k
        )

        vec_results, kw_results = await asyncio.gather(vec_task, kw_task)

        # Deduplicate by fragment_id
        seen = set()
        merged = []
        for mem in vec_results + kw_results:
            frag_id = mem.metadata.get("fragment_id") or mem.id
            if frag_id not in seen:
                seen.add(frag_id)
                merged.append(mem)

        return merged

    async def _report_error(self, error: Exception) -> None:
        """Helper to report errors."""
        try:
            from function import func
            await func.report_error(error)
        except Exception:
            logger.exception("Failed to report error")