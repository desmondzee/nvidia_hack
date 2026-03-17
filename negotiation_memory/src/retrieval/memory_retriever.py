"""Retrieve relevant historical negotiations from the vector store."""

from __future__ import annotations

import logging

from src.embeddings.nvidia_embedder import NvidiaEmbedder
from src.models.memory_models import (
    MemoryEntry,
    RetrieveRequest,
    RetrieveResponse,
)
from src.store.vector_store import MemoryVectorStore

logger = logging.getLogger(__name__)


class MemoryRetriever:
    def __init__(self, embedder: NvidiaEmbedder, store: MemoryVectorStore) -> None:
        self._embedder = embedder
        self._store = store

    async def retrieve(self, req: RetrieveRequest) -> RetrieveResponse:
        """
        Embed the query with NVIDIA NIM then do a COSINE similarity search in Milvus.
        Optionally filter by satellite IDs and/or entry type.
        """
        query_vec = await self._embedder.embed_one(req.query)

        # Decide which entry types to search
        if req.include_negotiations and not req.include_documents:
            type_filter = "negotiation"
        elif req.include_documents and not req.include_negotiations:
            type_filter = "document"
        else:
            type_filter = None

        hits = await self._store.search(
            query_embedding=query_vec,
            n_results=req.n_results,
            entry_type_filter=type_filter,
            satellite_id_filter=req.satellite_ids or None,
        )

        entries = [
            MemoryEntry(
                entry_id=h["entry_id"],
                entry_type=h["entry_type"],
                similarity_score=h["similarity_score"],
                summary=h["summary"],
                full_text=h["full_text"],
                metadata=h["metadata"],
            )
            for h in hits
            if h["similarity_score"] >= req.min_similarity
        ]

        logger.info(
            "Retrieved %d results for query: %s...", len(entries), req.query[:60]
        )
        return RetrieveResponse(
            results=entries,
            total_found=len(entries),
            query_used=req.query,
        )
