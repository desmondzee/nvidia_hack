"""
Milvus vector store using HNSW index.

Note: GPU_CAGRA doesn't work on GB10 (SM12x) — HNSW is the right index here.
Uses milvus-lite (local .db file) by default; set MILVUS_URI for a full server.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusClient,
    connections,
    utility,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "negotiation_memory"
EMBEDDING_DIM = int(os.getenv("NVIDIA_EMBEDDING_DIM", "1024"))

# milvus-lite: persist to a local file (no Docker needed for GB10 dev)
# For production Milvus server with GPU accel, set MILVUS_URI=http://localhost:19530
MILVUS_URI = os.getenv("MILVUS_URI", "")
MILVUS_DB_PATH = os.getenv(
    "MILVUS_DB_PATH",
    str(Path(__file__).resolve().parents[3] / "data" / "milvus_memory.db"),
)

# HNSW params — tuned for GB10 (20 Grace cores, 128 GB unified mem)
# M=16: graph connectivity; higher M = better recall, more RAM
# efConstruction=200: build-time search depth; higher = better graph quality
HNSW_M = int(os.getenv("HNSW_M", "16"))
HNSW_EF_CONSTRUCTION = int(os.getenv("HNSW_EF_CONSTRUCTION", "200"))
# ef (search): set per-query via search_params; 64 is a good default
HNSW_EF_SEARCH = int(os.getenv("HNSW_EF_SEARCH", "64"))


class MemoryVectorStore:
    """
    Thin async-friendly wrapper around Milvus (or milvus-lite).

    Call `await store.startup()` before use; `await store.shutdown()` to close.
    All heavy I/O is offloaded to asyncio.to_thread so it doesn't block the
    FastAPI event loop.
    """

    def __init__(self) -> None:
        self._client: MilvusClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        import asyncio

        await asyncio.to_thread(self._sync_startup)

    def _sync_startup(self) -> None:
        uri = MILVUS_URI if MILVUS_URI else MILVUS_DB_PATH
        Path(MILVUS_DB_PATH).parent.mkdir(parents=True, exist_ok=True)

        logger.info("Connecting to Milvus at %s", uri)
        self._client = MilvusClient(uri=uri)
        self._ensure_collection()
        logger.info("Milvus ready — collection '%s'", COLLECTION_NAME)

    async def shutdown(self) -> None:
        # MilvusClient closes automatically; nothing explicit needed for milvus-lite
        self._client = None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def insert(
        self,
        entry_id: str,
        entry_type: str,
        satellite_ids: list[str],
        embedding: list[float],
        full_text: str,
        summary: str,
        metadata: dict,
    ) -> None:
        import asyncio

        await asyncio.to_thread(
            self._sync_insert,
            entry_id,
            entry_type,
            satellite_ids,
            embedding,
            full_text,
            summary,
            metadata,
        )

    def _sync_insert(
        self,
        entry_id: str,
        entry_type: str,
        satellite_ids: list[str],
        embedding: list[float],
        full_text: str,
        summary: str,
        metadata: dict,
    ) -> None:
        assert self._client is not None
        row = {
            "entry_id": entry_id,
            "entry_type": entry_type,
            "satellite_ids": json.dumps(satellite_ids),
            "embedding": embedding,
            "full_text": full_text[:65535],
            "summary": summary[:2048],
            "metadata_json": json.dumps(metadata)[:8192],
            "created_at": int(time.time() * 1000),
        }
        self._client.insert(collection_name=COLLECTION_NAME, data=[row])

    async def search(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        entry_type_filter: str | None = None,
        satellite_id_filter: list[str] | None = None,
    ) -> list[dict]:
        import asyncio

        return await asyncio.to_thread(
            self._sync_search,
            query_embedding,
            n_results,
            entry_type_filter,
            satellite_id_filter,
        )

    def _sync_search(
        self,
        query_embedding: list[float],
        n_results: int,
        entry_type_filter: str | None,
        satellite_id_filter: list[str] | None,
    ) -> list[dict]:
        assert self._client is not None

        filters: list[str] = []
        if entry_type_filter:
            filters.append(f'entry_type == "{entry_type_filter}"')

        # Satellite filter: check if any of the requested IDs appear in the JSON list
        if satellite_id_filter:
            sat_clauses = " or ".join(
                f'satellite_ids like "%{sid}%"' for sid in satellite_id_filter
            )
            filters.append(f"({sat_clauses})")

        filter_expr = " and ".join(filters) if filters else ""

        results = self._client.search(
            collection_name=COLLECTION_NAME,
            data=[query_embedding],
            limit=n_results,
            filter=filter_expr or None,
            output_fields=[
                "entry_id",
                "entry_type",
                "satellite_ids",
                "full_text",
                "summary",
                "metadata_json",
                "created_at",
            ],
            search_params={
                "metric_type": "COSINE",
                "params": {"ef": HNSW_EF_SEARCH},
            },
        )

        hits = []
        for result_set in results:
            for hit in result_set:
                entity = hit.get("entity", {})
                hits.append(
                    {
                        "entry_id": entity.get("entry_id"),
                        "entry_type": entity.get("entry_type"),
                        "satellite_ids": json.loads(entity.get("satellite_ids", "[]")),
                        "full_text": entity.get("full_text", ""),
                        "summary": entity.get("summary", ""),
                        "metadata": json.loads(entity.get("metadata_json", "{}")),
                        "similarity_score": float(hit.get("distance", 0.0)),
                    }
                )
        return hits

    async def get_by_satellite(self, satellite_id: str, limit: int = 50) -> list[dict]:
        import asyncio

        return await asyncio.to_thread(self._sync_get_by_satellite, satellite_id, limit)

    def _sync_get_by_satellite(self, satellite_id: str, limit: int) -> list[dict]:
        assert self._client is not None
        results = self._client.query(
            collection_name=COLLECTION_NAME,
            filter=f'satellite_ids like "%{satellite_id}%"',
            output_fields=[
                "entry_id",
                "entry_type",
                "satellite_ids",
                "summary",
                "metadata_json",
                "created_at",
            ],
            limit=limit,
        )
        return [
            {
                "entry_id": r["entry_id"],
                "entry_type": r["entry_type"],
                "satellite_ids": json.loads(r.get("satellite_ids", "[]")),
                "summary": r.get("summary", ""),
                "metadata": json.loads(r.get("metadata_json", "{}")),
                "created_at": r.get("created_at"),
            }
            for r in results
        ]

    async def count(self) -> int:
        import asyncio

        return await asyncio.to_thread(self._sync_count)

    def _sync_count(self) -> int:
        assert self._client is not None
        stats = self._client.get_collection_stats(COLLECTION_NAME)
        return int(stats.get("row_count", 0))

    # ------------------------------------------------------------------
    # Collection setup
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        assert self._client is not None
        if self._client.has_collection(COLLECTION_NAME):
            logger.info("Collection '%s' already exists", COLLECTION_NAME)
            return

        logger.info("Creating collection '%s'", COLLECTION_NAME)
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)

        schema.add_field("entry_id", DataType.VARCHAR, max_length=128, is_primary=True)
        schema.add_field("entry_type", DataType.VARCHAR, max_length=32)
        schema.add_field("satellite_ids", DataType.VARCHAR, max_length=512)
        schema.add_field(
            "embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM
        )
        schema.add_field("full_text", DataType.VARCHAR, max_length=65535)
        schema.add_field("summary", DataType.VARCHAR, max_length=2048)
        schema.add_field("metadata_json", DataType.VARCHAR, max_length=8192)
        schema.add_field("created_at", DataType.INT64)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": HNSW_M, "efConstruction": HNSW_EF_CONSTRUCTION},
        )
        index_params.add_index(
            field_name="entry_type",
            index_type="Trie",  # fast scalar filter on a low-cardinality string field
        )

        self._client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )
        logger.info(
            "Collection created with HNSW index (M=%d, efConstruction=%d)",
            HNSW_M,
            HNSW_EF_CONSTRUCTION,
        )
