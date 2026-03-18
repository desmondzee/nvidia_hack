"""
Negotiation Memory Service
--------------------------
FastAPI app that stores and retrieves historical satellite negotiations using
NVIDIA NIM embeddings + Milvus vector search.

Endpoints:
  POST /memory/store-negotiation   — store a completed negotiation session
  POST /memory/store-document      — store an informational document
  POST /memory/retrieve            — semantic search over stored memory
  GET  /memory/history/{sat_id}    — all past negotiations for a satellite
  GET  /memory/stats               — collection stats
  GET  /health                     — liveness check
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.embeddings.nvidia_embedder import NvidiaEmbedder
from src.ingestion.negotiation_ingester import NegotiationIngester
from src.models.memory_models import (
    RetrieveRequest,
    RetrieveResponse,
    SatelliteHistoryResponse,
    StoreDocumentRequest,
    StoreNegotiationRequest,
)
from src.retrieval.memory_retriever import MemoryRetriever
from src.store.vector_store import MemoryVectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

embedder = NvidiaEmbedder()
store = MemoryVectorStore()
ingester = NegotiationIngester(embedder, store)
retriever = MemoryRetriever(embedder, store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up negotiation memory service...")
    await store.startup()
    await embedder.startup()
    logger.info("Memory service ready.")
    yield
    logger.info("Shutting down...")
    await embedder.shutdown()
    await ingester.shutdown()
    await store.shutdown()


app = FastAPI(
    title="Negotiation Memory Service",
    description="RAG memory for satellite negotiation agents — powered by NVIDIA NIM + Milvus",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/memory/store-negotiation", status_code=201)
async def store_negotiation(req: StoreNegotiationRequest) -> dict:
    """Store a completed negotiation session."""
    entry_id = await ingester.ingest_negotiation(req)
    return {"entry_id": entry_id, "session_id": req.session_id}


@app.post("/memory/store-document", status_code=201)
async def store_document(req: StoreDocumentRequest) -> dict:
    """Store an informational document (policy, space law, maneuver guide, etc.)."""
    entry_id = await ingester.ingest_document(req)
    return {"entry_id": entry_id, "document_id": req.document_id}


@app.post("/memory/retrieve", response_model=RetrieveResponse)
async def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    """
    Semantic search over stored negotiations and documents.

    Provide a natural language query describing the current situation.
    Optionally filter by satellite_ids to prioritise history involving
    the satellites currently negotiating.
    """
    return await retriever.retrieve(req)


@app.get("/memory/history/{satellite_id}", response_model=SatelliteHistoryResponse)
async def satellite_history(satellite_id: str) -> SatelliteHistoryResponse:
    """Return all past negotiations involving a given satellite."""
    rows = await store.get_by_satellite(satellite_id)
    negotiations = [r for r in rows if r["entry_type"] == "negotiation"]
    agreed_count = sum(1 for n in negotiations if n.get("metadata", {}).get("agreed"))
    return SatelliteHistoryResponse(
        satellite_id=satellite_id,
        total_negotiations=len(negotiations),
        agreed_count=agreed_count,
        negotiations=negotiations,
    )


@app.get("/memory/stats")
async def stats() -> dict:
    """Return collection statistics."""
    total = await store.count()
    return {"total_entries": total, "collection": "negotiation_memory"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("memory_api:app", host="0.0.0.0", port=8001, reload=False)
