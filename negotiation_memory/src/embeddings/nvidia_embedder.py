"""
NVIDIA NIM embedding client for the GB10 Grace Blackwell.

- Primary: local NIM microservice at localhost:8080 (on-chip, GPU-accelerated)
- Fallback: NVIDIA cloud API
- Batches requests (default 64) to keep the GPU busy
- Auto-detects local NIM on startup and falls back to cloud if unreachable
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOCAL_NIM_BASE_URL = os.getenv("LOCAL_NIM_BASE_URL", "http://localhost:8080/v1")
NVIDIA_API_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

# llama-3.2-nv-embedqa-1b-v2 is a 1.2 B-param model — fast on GB10, 1024-dim output
EMBEDDING_MODEL = os.getenv(
    "NVIDIA_EMBEDDING_MODEL", "nvidia/llama-3.2-nv-embedqa-1b-v2"
)
EMBEDDING_DIM = int(os.getenv("NVIDIA_EMBEDDING_DIM", "1024"))

# GB10-tuned batch size — fills Blackwell cores without exhausting 128 GB unified mem
BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "64"))

# Max concurrent in-flight HTTP requests to the NIM service
MAX_CONCURRENT_REQUESTS = int(os.getenv("EMBED_MAX_CONCURRENCY", "8"))

# 20 Grace cores for CPU-side text serialisation
CPU_WORKERS = int(os.getenv("CPU_WORKERS", "20"))


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class EmbedResult(BaseModel):
    embeddings: list[list[float]]
    model: str
    total_tokens: int
    latency_ms: float


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------


class NvidiaEmbedder:
    """
    Async embedder backed by a local NVIDIA NIM microservice.

    Usage::

        embedder = NvidiaEmbedder()
        await embedder.startup()           # verifies NIM reachability
        vecs = await embedder.embed(texts) # list[list[float]]
        await embedder.shutdown()
    """

    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self._executor = ThreadPoolExecutor(
            max_workers=CPU_WORKERS, thread_name_prefix="gb10-embed-cpu"
        )
        self._client: httpx.AsyncClient | None = None
        self._use_local = True  # flipped to False if local NIM unreachable

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Create shared HTTP client and probe local NIM availability."""
        # Long timeouts: NIM may need a moment to warm up on first request
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0),
            http2=True,  # NIM supports HTTP/2 — reduces per-request overhead
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )
        await self._probe_local_nim()

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
        self._executor.shutdown(wait=False)

    async def _probe_local_nim(self) -> None:
        """Check if local NIM is reachable; fall back to cloud API if not."""
        assert self._client is not None
        try:
            resp = await self._client.get(
                f"{LOCAL_NIM_BASE_URL}/models", timeout=3.0
            )
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                logger.info(
                    "Local NIM reachable — %d model(s) available: %s",
                    len(models),
                    [m.get("id") for m in models],
                )
                self._use_local = True
                return
        except Exception as exc:
            logger.warning("Local NIM probe failed (%s) — falling back to NVIDIA cloud API", exc)
        self._use_local = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed *texts* and return a list of float vectors.

        Internally splits into BATCH_SIZE chunks and fires them concurrently
        (bounded by MAX_CONCURRENT_REQUESTS) to maximise GPU throughput on the GB10.
        """
        if not texts:
            return []

        loop = asyncio.get_running_loop()

        # CPU-side text cleanup runs on Grace executor (non-blocking)
        cleaned: list[str] = await loop.run_in_executor(
            self._executor, _clean_texts, texts
        )

        batches = [
            cleaned[i : i + BATCH_SIZE] for i in range(0, len(cleaned), BATCH_SIZE)
        ]

        # Scatter all batches concurrently (semaphore caps in-flight count)
        tasks = [self._embed_batch(b) for b in batches]
        results: list[list[list[float]]] = await asyncio.gather(*tasks)

        # Flatten batch results maintaining original order
        all_embeddings: list[list[float]] = []
        for batch_vecs in results:
            all_embeddings.extend(batch_vecs)
        return all_embeddings

    async def embed_one(self, text: str) -> list[float]:
        vecs = await self.embed([text])
        return vecs[0]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        """Send one batch to NIM, retrying once on transient failure."""
        async with self._sem:
            for attempt in range(2):
                try:
                    return await self._call_nim(batch)
                except Exception as exc:
                    if attempt == 0:
                        logger.warning("Embedding batch failed (attempt 1): %s — retrying", exc)
                        await asyncio.sleep(0.5)
                    else:
                        logger.error("Embedding batch failed (attempt 2): %s", exc)
                        raise
        raise RuntimeError("unreachable")

    async def _call_nim(self, batch: list[str]) -> list[list[float]]:
        assert self._client is not None

        base_url = LOCAL_NIM_BASE_URL if self._use_local else NVIDIA_API_BASE_URL
        url = f"{base_url}/embeddings"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if not self._use_local and NVIDIA_API_KEY:
            headers["Authorization"] = f"Bearer {NVIDIA_API_KEY}"

        payload: dict[str, Any] = {
            "model": EMBEDDING_MODEL,
            "input": batch,
            # Ask NIM to return FP16 to halve payload size — Blackwell natively handles FP16
            "encoding_format": "float",
            "input_type": "passage",  # NV-EmbedQA distinguishes passage vs query at inference
        }

        t0 = time.perf_counter()
        resp = await self._client.post(url, json=payload, headers=headers)
        latency_ms = (time.perf_counter() - t0) * 1000

        resp.raise_for_status()
        data = resp.json()

        # NIM returns {"data": [{"embedding": [...], "index": i}, ...], "usage": {...}}
        embeddings_raw: list[dict[str, Any]] = data["data"]
        # Sort by index to guarantee original order (NIM may reorder for GPU efficiency)
        embeddings_raw.sort(key=lambda x: x["index"])
        embeddings = [item["embedding"] for item in embeddings_raw]

        tokens = data.get("usage", {}).get("total_tokens", 0)
        logger.debug(
            "Embedded %d texts | tokens=%d | latency=%.1f ms | local=%s",
            len(batch),
            tokens,
            latency_ms,
            self._use_local,
        )

        return embeddings


# ---------------------------------------------------------------------------
# CPU-side helper (runs in Grace executor)
# ---------------------------------------------------------------------------


def _clean_texts(texts: list[str]) -> list[str]:
    """
    Lightweight text normalisation on the Grace CPU cores.

    NIM's tokeniser handles most normalisation, so we just truncate extreme
    outliers to avoid exceeding the 512-token context window of EmbedQA models.
    Max ~2 000 chars ≈ ~500 tokens with typical English text.
    """
    MAX_CHARS = 2000
    cleaned = []
    for t in texts:
        t = t.strip()
        if len(t) > MAX_CHARS:
            t = t[:MAX_CHARS]
        if not t:
            t = "<empty>"
        cleaned.append(t)
    return cleaned
