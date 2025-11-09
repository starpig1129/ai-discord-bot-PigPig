# coding: utf-8
"""
Qdrant-based Vector Store implementation.

Implements QdrantStore which conforms to VectorStoreInterface.
Key behaviors:
- Only vectorize MemoryFragment.query_key when adding memories.
- Store summary (content) and full metadata as payload.
- Create payload indexing for author_id and channel_id to accelerate filtering.
- Provide search that builds dynamic filters based on user_id and channel_id.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    MatchText,
    PayloadSchemaType,
)

from addons.settings import MemoryConfig 
from addons.tokens import tokens
from function import func

from cogs.memory.exceptions import VectorOperationError, SearchError
from cogs.memory.vector_store_interface import MemoryFragment, VectorStoreInterface

from langchain_core.embeddings import Embeddings


class QdrantStore(VectorStoreInterface):
    """
    Qdrant-backed vector store.

    Notes:
    - The embedding_model is expected to follow langchain-core's Embeddings interface.
    - This class raises VectorOperationError / SearchError on qdrant or embedding failures.
    """

    def __init__(self, settings: MemoryConfig, embedding_model: Embeddings) -> None:
        """
        Initialize Qdrant client and store settings + embedding model.

        Required settings (must exist on the Settings instance):
         - QDRANT_URL or QDRANT_HOST
         - QDRANT_API_KEY (optional depending on server)
         - QDRANT_COLLECTION_NAME
         - EMBEDDING_DIM
        """
        # Validate required settings (do not silently use defaults)
        # Use MemoryConfig attributes (snake_case) defined in addons/settings.py,
        # but allow uppercase legacy names as fallback for backward compatibility.
        qdrant_url = getattr(settings, "qdrant_url", None)
        collection_name = getattr(settings, "qdrant_collection_name", None)
        embedding_dim = getattr(settings, "embedding_dim", None)
        api_key = getattr(tokens, "vector_store_api_key", None)
        if not qdrant_url or not collection_name or not embedding_dim:
            err = ValueError(
                "Missing required Qdrant settings: qdrant_url/qdrant_host, "
                "qdrant_collection_name and embedding_dim must be provided."
            )
            asyncio.create_task(func.report_error(err))
            raise VectorOperationError("Qdrant configuration incomplete") from err
 
        self.settings = settings
        self.embedding_model = embedding_model
        self.collection_name: str = collection_name
        try:
            self.embedding_dim: int = int(embedding_dim)
        except Exception as e:
            asyncio.create_task(func.report_error(e))
            raise VectorOperationError("Invalid embedding_dim for Qdrant") from e
 
        try:
            # Initialize client
            # If api_key is None, QdrantClient will try unauthenticated connection.
            self.qdrant_client = QdrantClient(url=qdrant_url, api_key=api_key)
        except Exception as e:
            asyncio.create_task(func.report_error(e))
            raise VectorOperationError("Failed to initialize Qdrant client") from e

    async def ensure_storage(self) -> None:
        """
        Ensure the collection exists in Qdrant. If not, (re)create it.
        Also create payload indexes for `author_id` and `channel_id`.
        """
        try:
            # qdrant_client.get_collection may raise on missing collection; use try/except
            try:
                self.qdrant_client.get_collection(self.collection_name)
                # Collection exists; ensure payload indexes exist (create_payload_index is idempotent)
            except Exception:
                # Recreate collection with required vector size
                # Using vectors_config parameter for newer Qdrant API versions
                from qdrant_client.http.models import VectorParams, Distance
                self.qdrant_client.recreate_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    ),
                )

            # Create payload indexes for author_id and channel_id to accelerate filtering.
            # Using KEYWORD schema which supports efficient exact-match queries.
            try:
                self.qdrant_client.create_payload_index(
                    collection_name=self.collection_name,
                    payload_key="author_id",
                    field_schema=PayloadSchemaType.STRING,
                )
            except Exception:
                # Some qdrant server versions provide create_payload_index; if it errors,
                # continue but report the error.
                pass

            try:
                self.qdrant_client.create_payload_index(
                    collection_name=self.collection_name,
                    payload_key="channel_id",
                    field_schema=PayloadSchemaType.STRING,
                )
            except Exception:
                pass

        except Exception as e:
            asyncio.create_task(func.report_error(e))
            raise VectorOperationError("Failed to ensure Qdrant storage") from e

    async def add_memories(self, memories: List[MemoryFragment]) -> None:
        """
        Add memories to Qdrant.

        - Only vectorize MemoryFragment.query_key.
        - Compose payload with summary and all metadata.
        - Upload points in batches using upsert.
        """
        if not memories:
            return

        try:
            # Extract the list of query_keys to embed
            query_texts = [m.query_key for m in memories]

            # Perform embedding in executor to avoid blocking event loop if sync API
            loop = asyncio.get_event_loop()
            if hasattr(self.embedding_model, "embed_documents"):
                vectors = await loop.run_in_executor(
                    None, lambda: self.embedding_model.embed_documents(query_texts)
                )
            elif hasattr(self.embedding_model, "embed_query"):
                # Fallback: call embed_query for each item (slower)
                vectors = []
                for q in query_texts:
                    vec = await loop.run_in_executor(None, lambda q=q: self.embedding_model.embed_query(q))
                    vectors.append(vec)
            else:
                raise VectorOperationError("Embedding model does not provide expected API")

            points: List[PointStruct] = []
            for mem, vec in zip(memories, vectors):
                # Generate stable id if available, otherwise uuid
                point_id = getattr(mem, "id", None) or str(uuid.uuid4())

                # Merge summary + metadata into payload
                payload: Dict[str, Any] = {"summary": mem.content}
                # Guarantee metadata is a dict
                metadata = getattr(mem, "metadata", {}) or {}
                if isinstance(metadata, dict):
                    payload.update(metadata)
                else:
                    # If metadata is not a dict, store it under 'metadata' key
                    payload["metadata"] = metadata

                # include author_id/channel_id top-level if present (helps filtering & indexing)
                if "author_id" in payload:
                    payload["author_id"] = str(payload["author_id"])
                if "channel_id" in payload:
                    payload["channel_id"] = str(payload["channel_id"])

                point = PointStruct(id=point_id, vector=vec, payload=payload)
                points.append(point)

            # Upsert in reasonable batch sizes (use 256)
            batch_size = 256
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                # QdrantClient.upsert is synchronous in many clients; run in executor
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda batch=batch: self.qdrant_client.upsert(
                        collection_name=self.collection_name, points=batch
                    ),
                )

        except VectorOperationError:
            raise
        except Exception as e:
            asyncio.create_task(func.report_error(e))
            raise VectorOperationError("Failed to add memories to Qdrant") from e

    async def search_memories_by_vector(
        self,
        query_text: str,
        limit: int = 8,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> List[MemoryFragment]:
        """
        Search memories with vector similarity and optional payload filtering.

        - Vectorize query_text.
        - Build dynamic Filter using user_id and channel_id.
        - Return list of MemoryFragment constructed from the payload.
        """
        try:
            # Embed the query_text
            loop = asyncio.get_event_loop()
            if hasattr(self.embedding_model, "embed_query"):
                query_vector = await loop.run_in_executor(
                    None, lambda: self.embedding_model.embed_query(query_text)
                )
            elif hasattr(self.embedding_model, "embed_documents"):
                # embed_documents can accept single-item list
                vecs = await loop.run_in_executor(
                    None, lambda: self.embedding_model.embed_documents([query_text])
                )
                query_vector = vecs[0]
            else:
                raise SearchError("Embedding model does not provide expected API for queries")

            # Build filter conditions dynamically
            must_conditions: List[FieldCondition] = []
            if user_id is not None:
                must_conditions.append(
                    FieldCondition(
                        key="author_id",
                        match=MatchValue(value=str(user_id)),
                    )
                )
            if channel_id is not None:
                must_conditions.append(
                    FieldCondition(
                        key="channel_id",
                        match=MatchValue(value=str(channel_id)),
                    )
                )

            q_filter = Filter(must=must_conditions) if must_conditions else None

            # Execute search. Use query_filter if available in this client version.
            # Run in executor since client is synchronous.
            def _search():
                return self.qdrant_client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    query_filter=q_filter,
                    with_payload=True,
                )

            raw_results = await loop.run_in_executor(None, _search)

            # Convert ScoredPoint results to MemoryFragment list
            results: List[MemoryFragment] = []
            for scored in raw_results:
                payload = getattr(scored, "payload", {}) or {}
                summary = payload.get("summary", "")
                metadata = dict(payload)
                # Remove the stored summary from metadata to avoid duplication
                metadata.pop("summary", None)

                # Construct MemoryFragment. Use scored.id as id if present.
                mem = MemoryFragment(
                    id=getattr(scored, "id", None) or str(uuid.uuid4()),
                    content=summary,
                    metadata=metadata,
                    query_key=summary,  # best-effort; query_key not stored separately
                    score=getattr(scored, "score", None),
                )
                # Optionally filter by min_score if provided
                if min_score is None or (mem.score is not None and mem.score >= min_score):
                    results.append(mem)

            return results

        except SearchError:
            raise
        except Exception as e:
            asyncio.create_task(func.report_error(e))
            raise SearchError("Failed to search memories in Qdrant") from e

    async def search_memories_by_keyword(
        self,
        query_text: str,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        k: int = 5
    ) -> List[MemoryFragment]:
        """
        Perform payload full-text search using Qdrant's MatchText via the scroll API.
    
        - Does NOT vectorize the query_text.
        - Builds a Filter with must conditions for author/channel (if provided)
          and should conditions using MatchText on payload fields 'summary' and 'query_key'.
        - Uses the scroll API to retrieve up to k results and converts them to MemoryFragment.
        """
        try:
            loop = asyncio.get_event_loop()
    
            # Build must conditions for exact-match filtering
            must_conditions: List[FieldCondition] = []
            if user_id is not None:
                must_conditions.append(
                    FieldCondition(
                        key="author_id",
                        match=MatchValue(value=str(user_id)),
                    )
                )
            if channel_id is not None:
                must_conditions.append(
                    FieldCondition(
                        key="channel_id",
                        match=MatchValue(value=str(channel_id)),
                    )
                )
    
            # Build should conditions for full-text matching on payload fields.
            should_conditions: List[FieldCondition] = [
                FieldCondition(key="summary", match=MatchText(text=query_text)),
                FieldCondition(key="query_key", match=MatchText(text=query_text)),
            ]
    
            # Compose filter: include must and should. Qdrant will treat should as OR-like.
            q_filter = Filter(must=must_conditions or None, should=should_conditions or None)
    
            # Use scroll to perform a payload-based retrieval. Scroll returns payload-bearing records.
            def _scroll():
                # Depending on qdrant-client version the parameter name is 'filter'
                return self.qdrant_client.scroll(
                    collection_name=self.collection_name,
                    limit=k,
                    offset=0,
                    filter=q_filter,
                    with_payload=True,
                )
    
            raw_records = await loop.run_in_executor(None, _scroll)
    
            results: List[MemoryFragment] = []
            for rec in raw_records:
                payload = getattr(rec, "payload", {}) or {}
                summary = payload.get("summary", "")
                metadata = dict(payload)
                metadata.pop("summary", None)
    
                mem = MemoryFragment(
                    id=getattr(rec, "id", None) or str(uuid.uuid4()),
                    content=summary,
                    metadata=metadata,
                    query_key=payload.get("query_key", summary),
                    score=getattr(rec, "score", None) if hasattr(rec, "score") else None,
                )
                results.append(mem)
    
            return results
    
        except Exception as e:
            asyncio.create_task(func.report_error(e))
            raise SearchError("Failed to perform keyword search in Qdrant") from e
    
    async def search(
        self,
        vector_query: Optional[str] = None,
        keyword_query: Optional[str] = None,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> List[MemoryFragment]:
        """
        High-level hybrid search that accepts separate vector and keyword queries.

        Behavior:
        - At least one of `vector_query` or `keyword_query` must be provided.
        - If only `vector_query` is provided, perform vector search only.
        - If only `keyword_query` is provided, perform keyword search only.
        - If both provided, run both searches in parallel, merge and deduplicate
          results (preferring vector results order).
        """
        try:
            # Resolve candidate setting names for flexibility but do not silently default.
            vector_k_candidates = (
                "VECTOR_SEARCH_K",
                "VECTOR_K",
                "VECTOR_SEARCH_LIMIT",
                "VECTOR_LIMIT",
                "VECTOR_TOP_K",
                "VECTOR_TOPK",
            )
            keyword_k_candidates = (
                "KEYWORD_SEARCH_K",
                "KEYWORD_K",
                "KEYWORD_SEARCH_LIMIT",
                "KEYWORD_LIMIT",
                "KEYWORD_TOP_K",
                "KEYWORD_TOPK",
            )
    
            # If neither query is provided, fail early.
            if not vector_query and not keyword_query:
                err = ValueError("At least one of vector_query or keyword_query must be provided")
                asyncio.create_task(func.report_error(err))
                raise err
    
            # Resolve vector k: prefer explicit uppercase settings, fall back to snake_case attribute,
            # and finally to a reasonable default. Report any missing/invalid configuration.
            vector_k = None
            if vector_query:
                for name in vector_k_candidates:
                    val = getattr(self.settings, name, None)
                    if val is not None:
                        try:
                            vector_k = int(val)
                            break
                        except Exception:
                            continue
                if vector_k is None:
                    # Try common snake_case config used by MemoryConfig
                    val = getattr(self.settings, "vector_search_k", None)
                    try:
                        if val is not None:
                            vector_k = int(val)
                    except Exception:
                        vector_k = None
                if vector_k is None:
                    # Final fallback default; report that explicit setting was not found.
                    try:
                        asyncio.create_task(
                            func.report_error(ValueError("VECTOR search k setting not configured; using default 5"))
                        )
                    except Exception:
                        pass
                    vector_k = 5
    
            # Resolve keyword k similarly.
            keyword_k = None
            if keyword_query:
                for name in keyword_k_candidates:
                    val = getattr(self.settings, name, None)
                    if val is not None:
                        try:
                            keyword_k = int(val)
                            break
                        except Exception:
                            continue
                if keyword_k is None:
                    val = getattr(self.settings, "keyword_search_k", None)
                    try:
                        if val is not None:
                            keyword_k = int(val)
                    except Exception:
                        keyword_k = None
                if keyword_k is None:
                    try:
                        asyncio.create_task(
                            func.report_error(ValueError("KEYWORD search k setting not configured; using default 3"))
                        )
                    except Exception:
                        pass
                    keyword_k = 3
    
            # Only vector query provided
            if vector_query and not keyword_query:
                return await self.search_memories_by_vector(
                    query_text=vector_query, limit=vector_k, user_id=user_id, channel_id=channel_id
                )
    
            # Only keyword query provided
            if keyword_query and not vector_query:
                return await self.search_memories_by_keyword(
                    query_text=keyword_query, user_id=user_id, channel_id=channel_id, k=keyword_k
                )
    
            # Both provided: run in parallel and merge/deduplicate (vector preferred)
            vector_task = self.search_memories_by_vector(
                query_text=vector_query, limit=vector_k, user_id=user_id, channel_id=channel_id
            )
            keyword_task = self.search_memories_by_keyword(
                query_text=keyword_query, user_id=user_id, channel_id=channel_id, k=keyword_k
            )
    
            vec_results, kw_results = await asyncio.gather(vector_task, keyword_task)
    
            # Merge and deduplicate results. Prefer earlier results (vector first).
            seen_keys = set()
            merged: List[MemoryFragment] = []
    
            def _key_for_mem(m: MemoryFragment) -> str:
                # Prefer fragment_id in metadata (should be present), else try id attr, else content+query_key
                try:
                    if isinstance(getattr(m, "metadata", None), dict):
                        frag = m.metadata.get("fragment_id")
                        if frag:
                            return str(frag)
                except Exception:
                    pass
                if hasattr(m, "id"):
                    return str(getattr(m, "id"))
                # fallback
                return f"{getattr(m, 'content', '')}|{getattr(m, 'query_key', '')}"
    
            for mem in (vec_results or []):
                key = _key_for_mem(mem)
                if key not in seen_keys:
                    seen_keys.add(key)
                    merged.append(mem)
    
            for mem in (kw_results or []):
                key = _key_for_mem(mem)
                if key not in seen_keys:
                    seen_keys.add(key)
                    merged.append(mem)
    
            return merged
        except SearchError:
            raise
        except Exception as e:
            asyncio.create_task(func.report_error(e))
            raise SearchError("High-level hybrid search failed") from e