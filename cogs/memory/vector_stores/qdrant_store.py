# cogs/memory/vector_stores/qdrant_store.py

import logging
from typing import Any, Dict, List, Optional

# Qdrant-specific imports
import qdrant_client
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    MatchValue,
    PointStruct,
    VectorParams,
    Filter,
    PayloadSchemaType
)

# Project-specific imports
from ..vector_store_interface import MemoryFragment, VectorStoreInterface
from ..exceptions import VectorOperationError, SearchError, IndexIntegrityError
from llm.model_manager import ModelManager
from addons.settings import memory_config
from addons.tokens import tokens 

logger = logging.getLogger(__name__)

class QdrantStore(VectorStoreInterface):
    """
    An implementation of the VectorStoreInterface using Qdrant as the backend.
    """

    def __init__(self, memory_config: Any, embedding_model: Any):
        """
        Initializes the Qdrant store.

        Args:
            memory_config: The memory configuration object.
            embedding_model: The embedding model instance.
        """
        self.collection_name = memory_config.vector_store.collection_name
        self.embedding_model = embedding_model
        
        try:
            self.client = qdrant_client.QdrantClient(
                host=memory_config.vector_store.host,
                port=memory_config.vector_store.port,
                api_key=tokens.vector_store_api_key,
            )
            logger.info("Qdrant client initialized successfully.")
            self.ensure_storage()
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant client: {e}")
            raise VectorOperationError("Could not connect to Qdrant.") from e

    def ensure_storage(self):
        """
        Ensures the collection exists in Qdrant and has the correct configuration and payload indexing.
        """
        try:
            self.client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.embedding_model.get_embedding_dim(), distance=Distance.COSINE),
            )
            # Create payload indexes for efficient filtering
            self.client.create_payload_index(collection_name=self.collection_name, field_name="author_id", field_schema=PayloadSchemaType.KEYWORD)
            self.client.create_payload_index(collection_name=self.collection_name, field_name="channel_id", field_schema=PayloadSchemaType.KEYWORD)
            self.client.create_payload_index(collection_name=self.collection_name, field_name="timestamp", field_schema=PayloadSchemaType.FLOAT)
            logger.info(f"Collection '{self.collection_name}' created/verified with payload indexing.")
        except Exception as e:
            logger.error(f"Failed to create or verify collection '{self.collection_name}': {e}")
            raise IndexIntegrityError("Failed to set up Qdrant collection and indexes.") from e

    async def add_memories(self, memories: List[MemoryFragment]) -> None:
        """
        Adds memory fragments to the Qdrant collection.
        It vectorizes the `query_key` and stores the `content` summary in the payload.
        """
        if not memories:
            return

        try:
            # IMPORTANT: Vectorize the `query_key`, not the `content`.
            vectors = await self.embedding_model.embed_documents([mem.query_key for mem in memories])
            
            points = []
            for i, mem in enumerate(memories):
                # IMPORTANT: Store the human-readable `content` in the payload, along with all metadata.
                payload = {"content": mem.content, **mem.metadata}
                
                point = PointStruct(
                    id=mem.metadata['fragment_id'],
                    vector=vectors[i],
                    payload=payload
                )
                points.append(point)

            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True  # Wait for the operation to complete
            )
            logger.info(f"Successfully upserted {len(points)} memory fragments.")
        except Exception as e:
            logger.error(f"Failed to add memories to Qdrant: {e}")
            raise VectorOperationError("Failed to upsert points to Qdrant.") from e

    async def search_memories(
        self,
        query_text: str,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        k: int = 5
    ) -> List[MemoryFragment]:
        """
        Performs a hybrid search in Qdrant using a query vector and metadata filters.
        """
        try:
            query_vector = await self.embedding_model.embed_query(query_text)
            
            # Build metadata filters for a precise search
            filter_must = []
            if user_id:
                filter_must.append(FieldCondition(key="author_id", match=MatchValue(value=user_id)))
            if channel_id:
                filter_must.append(FieldCondition(key="channel_id", match=MatchValue(value=channel_id)))

            search_filter = Filter(must=filter_must) if filter_must else None

            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=search_filter,
                limit=k,
                with_payload=True
            )

            # Convert ScoredPoint results back to MemoryFragment objects
            memory_fragments = []
            for point in results:
                if point.payload is None:
                    continue
                
                content = point.payload.pop("content", "")
                # The rest of the payload is the metadata
                metadata = point.payload
                
                # Reconstruct the query_key is not possible/needed for retrieval, so we can leave it empty.
                fragment = MemoryFragment(
                    content=content,
                    query_key="",
                    metadata=metadata if metadata is not None else {}
                )
                memory_fragments.append(fragment)
            
            logger.info(f"Found {len(memory_fragments)} relevant memories for query.")
            return memory_fragments
        except Exception as e:
            logger.error(f"Failed to search memories in Qdrant: {e}")
            raise SearchError("Failed during Qdrant search operation.") from e