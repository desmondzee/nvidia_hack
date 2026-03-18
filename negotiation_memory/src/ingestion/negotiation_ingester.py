"""
Convert completed negotiation sessions and documents into rich text, embed them,
and store them in the vector store.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from src.embeddings.nvidia_embedder import NvidiaEmbedder
from src.models.memory_models import StoreDocumentRequest, StoreNegotiationRequest
from src.store.vector_store import MemoryVectorStore

logger = logging.getLogger(__name__)

# 20 Grace cores for serialisation
CPU_WORKERS = 20


class NegotiationIngester:
    """
    Ingests negotiations and documents into the memory store.

    Both `ingest_negotiation` and `ingest_document` are async and safe to
    call concurrently from multiple FastAPI request handlers.
    """

    def __init__(self, embedder: NvidiaEmbedder, store: MemoryVectorStore) -> None:
        self._embedder = embedder
        self._store = store
        self._executor = ThreadPoolExecutor(max_workers=CPU_WORKERS)

    async def shutdown(self) -> None:
        self._executor.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def ingest_negotiation(self, req: StoreNegotiationRequest) -> str:
        """
        Build a rich narrative, embed it, and persist to Milvus.
        Returns the entry_id.
        """
        loop = asyncio.get_running_loop()

        # Serialise on Grace CPU cores (non-blocking)
        full_text, summary, metadata = await loop.run_in_executor(
            self._executor, _serialise_negotiation, req
        )

        # Embed on Blackwell GPU via local NIM
        embedding = await self._embedder.embed_one(full_text)

        satellite_ids = [req.initiator_satellite_id, req.responder_satellite_id]
        entry_id = _make_entry_id("negotiation", req.session_id)

        await self._store.insert(
            entry_id=entry_id,
            entry_type="negotiation",
            satellite_ids=satellite_ids,
            embedding=embedding,
            full_text=full_text,
            summary=summary,
            metadata=metadata,
        )

        logger.info(
            "Ingested negotiation %s (%s ↔ %s, agreed=%s)",
            req.session_id,
            req.initiator_satellite_id,
            req.responder_satellite_id,
            req.final_agreed,
        )
        return entry_id

    async def ingest_document(self, req: StoreDocumentRequest) -> str:
        """Embed and store an informational document."""
        loop = asyncio.get_running_loop()

        full_text, summary, metadata = await loop.run_in_executor(
            self._executor, _serialise_document, req
        )

        embedding = await self._embedder.embed_one(full_text)
        entry_id = _make_entry_id("document", req.document_id)

        await self._store.insert(
            entry_id=entry_id,
            entry_type="document",
            satellite_ids=[],
            embedding=embedding,
            full_text=full_text,
            summary=summary,
            metadata=metadata,
        )

        logger.info("Ingested document '%s' (category=%s)", req.title, req.category)
        return entry_id

    async def ingest_batch(self, reqs: list[StoreNegotiationRequest]) -> list[str]:
        """
        Ingest multiple negotiations concurrently.

        Text serialisation runs in parallel on the Grace executor; embeddings are
        batched to maximise Blackwell GPU throughput (batch_size=64 in the embedder).
        """
        loop = asyncio.get_running_loop()

        # Serialise all in parallel on Grace CPU
        serialised = await asyncio.gather(
            *[
                loop.run_in_executor(self._executor, _serialise_negotiation, req)
                for req in reqs
            ]
        )

        texts = [s[0] for s in serialised]

        embeddings = await self._embedder.embed(texts)

        entry_ids: list[str] = []
        for req, (full_text, summary, metadata), embedding in zip(
            reqs, serialised, embeddings
        ):
            entry_id = _make_entry_id("negotiation", req.session_id)
            await self._store.insert(
                entry_id=entry_id,
                entry_type="negotiation",
                satellite_ids=[req.initiator_satellite_id, req.responder_satellite_id],
                embedding=embedding,
                full_text=full_text,
                summary=summary,
                metadata=metadata,
            )
            entry_ids.append(entry_id)

        logger.info("Batch ingested %d negotiations", len(reqs))
        return entry_ids


# ---------------------------------------------------------------------------
# Pure serialisation functions — run on Grace CPU executor
# ---------------------------------------------------------------------------


def _serialise_negotiation(
    req: StoreNegotiationRequest,
) -> tuple[str, str, dict]:
    """
    Build a rich natural-language narrative of the negotiation for embedding.

    The richer the text, the better the semantic retrieval — we include
    physical parameters, reasoning snippets, and outcomes so that future
    queries like "close approach under 200m with Starlink" will match correctly.
    """
    tca_str = req.time_of_closest_approach.isoformat()
    negotiated_at_str = req.negotiated_at.isoformat()

    lines: list[str] = [
        f"Satellite negotiation session {req.session_id}",
        f"Initiator: {req.initiator_satellite_id} | Responder: {req.responder_satellite_id}",
        f"Alert ID: {req.alert_id}",
        f"Time of closest approach (TCA): {tca_str}",
        f"Miss distance: {req.miss_distance_m:.1f} m",
        f"Probability of collision: {req.probability_of_collision:.2e}",
        f"Threat level: {req.threat_level}",
    ]

    if req.relative_velocity_m_s is not None:
        lines.append(f"Relative velocity: {req.relative_velocity_m_s:.1f} m/s")
    if req.space_weather_kp is not None:
        lines.append(f"Space weather Kp index: {req.space_weather_kp:.1f}")
    if req.atmospheric_drag_factor is not None:
        lines.append(f"Atmospheric drag factor: {req.atmospheric_drag_factor:.4f}")

    lines.append(f"\nNegotiation ran for {req.rounds_taken} round(s).")

    for rnd in req.rounds:
        lines.append(f"\n--- Round {rnd.round_number} ---")
        lines.append(f"Initiator reasoning: {rnd.initiator_proposal}")
        lines.append(f"Responder reasoning: {rnd.responder_response}")
        if rnd.initiator_proposed_maneuver:
            m = rnd.initiator_proposed_maneuver
            lines.append(
                f"Initiator proposed maneuver: delta-v ({m.delta_v.x:.4f}, "
                f"{m.delta_v.y:.4f}, {m.delta_v.z:.4f}) m/s RTN, "
                f"duration {m.burn_duration_seconds:.1f}s, "
                f"expected miss after {m.expected_miss_distance_after_m:.0f}m"
            )
        if rnd.responder_counter_proposal:
            m = rnd.responder_counter_proposal
            lines.append(
                f"Responder counter-proposal: delta-v ({m.delta_v.x:.4f}, "
                f"{m.delta_v.y:.4f}, {m.delta_v.z:.4f}) m/s RTN, "
                f"duration {m.burn_duration_seconds:.1f}s, "
                f"expected miss after {m.expected_miss_distance_after_m:.0f}m"
            )
        lines.append(f"Round accepted: {rnd.accepted_this_round}")

    lines.append(f"\nOutcome: {'AGREEMENT REACHED' if req.final_agreed else 'NO AGREEMENT'}")

    if req.final_initiator_maneuver:
        m = req.final_initiator_maneuver
        lines.append(
            f"Final initiator maneuver: delta-v ({m.delta_v.x:.4f}, "
            f"{m.delta_v.y:.4f}, {m.delta_v.z:.4f}) m/s, "
            f"burn duration {m.burn_duration_seconds:.1f}s"
        )
    if req.final_responder_maneuver:
        m = req.final_responder_maneuver
        lines.append(
            f"Final responder maneuver: delta-v ({m.delta_v.x:.4f}, "
            f"{m.delta_v.y:.4f}, {m.delta_v.z:.4f}) m/s, "
            f"burn duration {m.burn_duration_seconds:.1f}s"
        )

    lines.append(f"\nSummary: {req.negotiation_summary}")

    if req.tags:
        lines.append(f"Tags: {', '.join(req.tags)}")

    full_text = "\n".join(lines)

    summary = (
        f"{req.initiator_satellite_id} ↔ {req.responder_satellite_id} | "
        f"miss={req.miss_distance_m:.0f}m | Pc={req.probability_of_collision:.1e} | "
        f"threat={req.threat_level} | agreed={req.final_agreed} | "
        f"rounds={req.rounds_taken} | {negotiated_at_str}"
    )

    metadata = {
        "session_id": req.session_id,
        "alert_id": req.alert_id,
        "initiator": req.initiator_satellite_id,
        "responder": req.responder_satellite_id,
        "miss_distance_m": req.miss_distance_m,
        "probability_of_collision": req.probability_of_collision,
        "threat_level": req.threat_level,
        "agreed": req.final_agreed,
        "rounds_taken": req.rounds_taken,
        "negotiated_at": req.negotiated_at.isoformat(),
        "tca": req.time_of_closest_approach.isoformat(),
        "tags": req.tags,
    }

    return full_text, summary, metadata


def _serialise_document(req: StoreDocumentRequest) -> tuple[str, str, dict]:
    full_text = f"Title: {req.title}\nCategory: {req.category}\n\n{req.content}"
    summary = f"[{req.category}] {req.title}"
    metadata = {
        "document_id": req.document_id,
        "title": req.title,
        "category": req.category,
        "tags": req.tags,
    }
    return full_text, summary, metadata


def _make_entry_id(entry_type: str, source_id: str) -> str:
    """Deterministic entry ID so re-ingesting the same session is idempotent."""
    h = hashlib.sha256(f"{entry_type}:{source_id}".encode()).hexdigest()[:16]
    return f"{entry_type[:3]}_{h}"
