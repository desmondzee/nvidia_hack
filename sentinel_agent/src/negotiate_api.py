"""FastAPI ingest endpoint for sentinel_agent.

Accepts an EnrichedCollisionAlert from satellite_traffic_api and runs the
LLM-based multi-round negotiation simulation, returning a ManeuverDecision.

Also includes streaming endpoints when run with: uvicorn src.negotiate_api:app --port 8001

Start with:
    uvicorn src.negotiate_api:app --port 8001 --reload
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from src.api.server import app as stream_app
from src.memory.client import MemoryClient
from src.models.enriched import EnrichedCollisionAlert
from src.models.maneuver import ManeuverDecision
from src.models.negotiation import NegotiationMessage
from src.simulation.runner import run_simulation_from_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

_LLM_PROVIDER = os.getenv("SENTINEL_LLM_PROVIDER", "nvidia")

memory_client = MemoryClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await memory_client.startup()
    yield
    await memory_client.shutdown()


app = FastAPI(
    title="Sentinel Agent API",
    description=(
        "Receives EnrichedCollisionAlert payloads from satellite_traffic_api and "
        "runs LLM-based multi-round negotiation to produce a ManeuverDecision. "
        "Also includes streaming endpoints for simulation demos."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Include streaming endpoints (six_satellite, etc.) so both entry points work
app.include_router(stream_app.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "llm_provider": _LLM_PROVIDER}


@app.post("/negotiate", response_model=ManeuverDecision | None)
async def negotiate(payload: EnrichedCollisionAlert) -> ManeuverDecision | None:
    """
    Run collision avoidance negotiation for the given enriched alert.

    RAG flow:
      1. Query negotiation_memory service for similar past negotiations
      2. Inject retrieved history into LLM prompts
      3. Run LangGraph negotiation (up to 3 rounds)
      4. Store the completed session back in negotiation_memory

    Returns a ManeuverDecision with:
      - agreed: whether both satellites reached an agreement
      - our_maneuver / peer_maneuver: proposed delta-V burns
      - negotiation_summary: LLM-generated plain-English summary
      - rounds_taken: number of negotiation rounds used
    """
    logger.info(
        "Received negotiation request: alert_id=%s risk=%s miss=%.1fm tca_in=%.0fs",
        payload.alert_id,
        payload.final_risk,
        payload.miss_distance_m,
        payload.time_to_tca_seconds,
    )

    alert = payload.to_collision_alert()

    # 1. Retrieve relevant historical context from the RAG memory service
    historical_context = await memory_client.retrieve_context(
        satellite_ids=[payload.our_object.object_id, payload.threat_object.object_id],
        miss_distance_m=payload.miss_distance_m,
        threat_level=payload.threat_level,
        probability_of_collision=payload.probability_of_collision,
    )
    if historical_context:
        logger.info("Injecting historical context (%d chars) into negotiation prompts", len(historical_context))

    # 2. Run negotiation with RAG context injected into LLM prompts
    try:
        decision, initiator_result = await run_simulation_from_alert(
            alert,
            llm_provider=_LLM_PROVIDER,
            historical_context=historical_context,
        )
    except Exception as exc:
        logger.exception("Negotiation simulation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Negotiation failed: {exc}")

    if decision:
        logger.info(
            "Negotiation complete: agreed=%s rounds=%d",
            decision.agreed,
            decision.rounds_taken,
        )

        # 3. Store the completed negotiation in the RAG memory service
        messages_log: list[NegotiationMessage] = [
            NegotiationMessage.model_validate(m) if isinstance(m, dict) else m
            for m in initiator_result.get("messages_log", [])
        ]
        await memory_client.store_negotiation(alert, decision, messages_log)
    else:
        logger.warning("Negotiation produced no decision for alert %s", payload.alert_id)

    return decision
