"""
HTTP client for the negotiation_memory RAG service.

Two responsibilities:
  - retrieve_context(): query before a negotiation starts so the LLM gets
    relevant historical examples in its prompt
  - store_negotiation(): persist a completed negotiation after it finishes
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from src.models.maneuver import ManeuverDecision
from src.models.negotiation import NegotiationMessage, NegotiationPhase
from src.models.physics import CollisionAlert

logger = logging.getLogger(__name__)

MEMORY_SERVICE_URL = os.getenv("MEMORY_SERVICE_URL", "http://localhost:8001")
MEMORY_TIMEOUT = float(os.getenv("MEMORY_TIMEOUT_SECONDS", "10"))


class MemoryClient:
    """Async client for the negotiation memory service."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=MEMORY_SERVICE_URL,
            timeout=MEMORY_TIMEOUT,
        )

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Retrieve — called BEFORE negotiation
    # ------------------------------------------------------------------

    async def retrieve_context(
        self,
        satellite_ids: list[str],
        miss_distance_m: float,
        threat_level: str,
        probability_of_collision: float,
        n_results: int = 4,
    ) -> str:
        """
        Query the memory service for similar past negotiations and return
        a formatted string ready to inject into the LLM system prompt.

        Returns an empty string if the memory service is unreachable (graceful degradation).
        """
        if not self._client:
            return ""

        query = (
            f"Satellite collision avoidance negotiation. "
            f"Miss distance {miss_distance_m:.0f}m, "
            f"probability of collision {probability_of_collision:.2e}, "
            f"threat level {threat_level}. "
            f"Satellites: {', '.join(satellite_ids)}."
        )

        try:
            resp = await self._client.post(
                "/memory/retrieve",
                json={
                    "query": query,
                    "satellite_ids": satellite_ids,
                    "n_results": n_results,
                    "include_negotiations": True,
                    "include_documents": True,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Memory service unreachable, skipping historical context: %s", exc)
            return ""

        results = data.get("results", [])
        if not results:
            return ""

        lines = ["HISTORICAL CONTEXT FROM SIMILAR PAST NEGOTIATIONS:"]
        for i, entry in enumerate(results, 1):
            score = entry.get("similarity_score", 0.0)
            lines.append(f"\n[{i}] (similarity {score:.2f}) {entry['summary']}")
            # Include the first 800 chars of full text for detail
            full = entry.get("full_text", "")
            if full:
                lines.append(full[:800])
        lines.append(
            "\nUse this history to inform your proposals — prefer strategies "
            "that worked in similar situations."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Store — called AFTER negotiation
    # ------------------------------------------------------------------

    async def store_negotiation(
        self,
        alert: CollisionAlert,
        decision: ManeuverDecision,
        messages_log: list[NegotiationMessage],
    ) -> None:
        """
        Persist a completed negotiation to the memory service.
        Fire-and-forget — failures are logged but not raised.
        """
        if not self._client:
            return

        try:
            payload = _build_store_payload(alert, decision, messages_log)
            resp = await self._client.post("/memory/store-negotiation", json=payload)
            resp.raise_for_status()
            logger.info("Stored negotiation %s in memory service", decision.session_id)
        except Exception as exc:
            logger.warning("Failed to store negotiation in memory service: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_store_payload(
    alert: CollisionAlert,
    decision: ManeuverDecision,
    messages_log: list[NegotiationMessage],
) -> dict:
    """Build the StoreNegotiationRequest payload dict from native agent models."""

    # Group messages by round number
    rounds_by_num: dict[int, dict] = {}
    for msg in messages_log:
        rn = msg.round_number
        if rn not in rounds_by_num:
            rounds_by_num[rn] = {"proposal": None, "response": None}
        if msg.phase == NegotiationPhase.PROPOSAL:
            rounds_by_num[rn]["proposal"] = msg
        else:
            rounds_by_num[rn]["response"] = msg

    rounds = []
    for rn, msgs in sorted(rounds_by_num.items()):
        proposal: NegotiationMessage | None = msgs["proposal"]
        response: NegotiationMessage | None = msgs["response"]
        rounds.append(
            {
                "round_number": rn,
                "initiator_proposal": proposal.reasoning if proposal else "",
                "responder_response": response.reasoning if response else "",
                "initiator_proposed_maneuver": _maneuver_dict(
                    proposal.proposed_maneuver if proposal else None
                ),
                "responder_counter_proposal": _maneuver_dict(
                    response.counter_proposal if response else None
                ),
                "accepted_this_round": bool(response.accepted) if response else False,
            }
        )

    return {
        "session_id": decision.session_id,
        "alert_id": decision.alert_id,
        "initiator_satellite_id": decision.our_satellite_id,
        "responder_satellite_id": decision.peer_satellite_id,
        "miss_distance_m": alert.miss_distance_m,
        "probability_of_collision": alert.probability_of_collision,
        "time_of_closest_approach": alert.time_of_closest_approach.isoformat(),
        "threat_level": alert.threat_level.value,
        "relative_velocity_m_s": _vec_magnitude(alert.relative_velocity) if alert.relative_velocity else None,
        "space_weather_kp": alert.weather_parameters.get("kp_index") if alert.weather_parameters else None,
        "rounds": rounds,
        "final_agreed": decision.agreed,
        "final_initiator_maneuver": _maneuver_dict(decision.our_maneuver),
        "final_responder_maneuver": _maneuver_dict(decision.peer_maneuver),
        "negotiation_summary": decision.negotiation_summary,
        "rounds_taken": decision.rounds_taken,
        "negotiated_at": datetime.now(timezone.utc).isoformat(),
    }


def _maneuver_dict(m) -> dict | None:
    if m is None:
        return None
    return {
        "delta_v": {"x": m.delta_v.x, "y": m.delta_v.y, "z": m.delta_v.z},
        "burn_start_time": m.burn_start_time.isoformat(),
        "burn_duration_seconds": m.burn_duration_seconds,
        "expected_miss_distance_after_m": m.expected_miss_distance_after_m,
        "fuel_cost_estimate": m.fuel_cost_estimate,
    }


def _vec_magnitude(v) -> float:
    import math
    return math.sqrt(v.x**2 + v.y**2 + v.z**2)
