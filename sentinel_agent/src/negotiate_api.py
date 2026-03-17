"""FastAPI ingest endpoint for sentinel_agent.

Accepts an EnrichedCollisionAlert from satellite_traffic_api and runs the
LLM-based multi-round negotiation simulation, returning a ManeuverDecision.

Start with:
    uvicorn src.negotiate_api:app --port 8001 --reload
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException

from src.models.enriched import EnrichedCollisionAlert
from src.models.maneuver import ManeuverDecision
from src.simulation.runner import run_simulation_from_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sentinel Agent API",
    description=(
        "Receives EnrichedCollisionAlert payloads from satellite_traffic_api and "
        "runs LLM-based multi-round negotiation to produce a ManeuverDecision."
    ),
    version="1.0.0",
)

_LLM_PROVIDER = os.getenv("SENTINEL_LLM_PROVIDER", "nvidia")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "llm_provider": _LLM_PROVIDER}


@app.post("/negotiate", response_model=ManeuverDecision | None)
async def negotiate(payload: EnrichedCollisionAlert) -> ManeuverDecision | None:
    """
    Run collision avoidance negotiation for the given enriched alert.

    Converts the EnrichedCollisionAlert to a CollisionAlert and runs the
    existing LangGraph negotiation graph (up to 3 rounds).

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

    try:
        decision, _ = await run_simulation_from_alert(alert, llm_provider=_LLM_PROVIDER)
    except Exception as exc:
        logger.exception("Negotiation simulation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Negotiation failed: {exc}")

    if decision:
        logger.info(
            "Negotiation complete: agreed=%s rounds=%d",
            decision.agreed,
            decision.rounds_taken,
        )
    else:
        logger.warning("Negotiation produced no decision for alert %s", payload.alert_id)

    return decision
