"""Negotiate endpoint: detects high-risk conjunctions and triggers sentinel_agent.

POST /v1/satellites/{norad_id}/negotiate

Workflow:
  1. Build full SatelliteContext (orbital state, conjunctions, weather, atmosphere)
  2. If final_risk < HIGH → return early with no_action status
  3. Identify worst conjunction (highest risk, earliest TCA as tiebreaker)
  4. Propagate both objects to TCA → full ECI state vectors
  5. Assemble EnrichedCollisionAlert with all context needed for holistic decisions
  6. POST to sentinel_agent /negotiate
  7. Return the alert payload and sentinel_agent's ManeuverDecision response
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from satellite_traffic_api.config import settings
from satellite_traffic_api.models.context import RiskLevel
from satellite_traffic_api.models.conjunction import ConjunctionEvent
from satellite_traffic_api.models.enriched_alert import (
    EnrichedCollisionAlert,
    EciVector,
    SpaceObjectPayload,
    ConjunctionSummary,
)
from satellite_traffic_api.models.orbital import StateVector

logger = logging.getLogger(__name__)
router = APIRouter(tags=["negotiation"])

_RISK_ORDER: dict[RiskLevel, int] = {"NOMINAL": 0, "ELEVATED": 1, "HIGH": 2, "CRITICAL": 3}
_RISK_TO_THREAT = {"NOMINAL": "low", "ELEVATED": "medium", "HIGH": "high", "CRITICAL": "critical"}


def _get_builder(request: Request):
    return request.app.state.context_builder


def _get_celestrak(request: Request):
    return request.app.state.celestrak


def _get_propagator(request: Request):
    return request.app.state.propagator


def _state_to_eci(state: StateVector) -> EciVector:
    return EciVector(x=state.x_km, y=state.y_km, z=state.z_km)


def _vel_to_eci(state: StateVector) -> EciVector:
    return EciVector(x=state.vx_km_s, y=state.vy_km_s, z=state.vz_km_s)


def _object_type_str(raw: str) -> str:
    """Normalise ConjunctionEvent object type to sentinel_agent convention."""
    return raw.lower().replace("_", "_")  # ROCKET_BODY → rocket_body, DEBRIS → debris


def _worst_conjunction(
    conjunctions: list[ConjunctionEvent], risk_order: dict[str, int]
) -> ConjunctionEvent | None:
    """Return the highest-risk conjunction, using earliest TCA as tiebreaker."""
    high_risk = [
        c for c in conjunctions
        if c.miss_distance_km < 1.0 or (c.collision_probability or 0) > 1e-4
    ]
    if not high_risk:
        # Fall back to closest miss
        sorted_all = sorted(conjunctions, key=lambda c: c.miss_distance_km)
        return sorted_all[0] if sorted_all else None
    return sorted(high_risk, key=lambda c: (c.miss_distance_km, c.tca))[0]


async def run_negotiate_pipeline(
    norad_id: int,
    builder,
    celestrak,
    propagator,
) -> dict:
    """
    Core negotiate logic, callable directly (not just via HTTP).

    Returns:
      - status="no_action" if risk < HIGH
      - status="triggered" with alert + sentinel_agent response if risk >= HIGH
      - status="alert_only" if sentinel_agent unreachable but alert was built
    """
    # Step 1: Build full satellite context
    try:
        ctx = await builder.build(norad_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Context build failed: {exc}")

    final_risk: RiskLevel = ctx.collision_risk_level  # type: ignore[assignment]

    # Step 2: Early exit if not high enough risk
    if _RISK_ORDER[final_risk] < _RISK_ORDER["HIGH"]:
        return {
            "status": "no_action",
            "risk_level": final_risk,
            "message": "Risk below HIGH threshold. No negotiation required.",
        }

    # Step 3: Pick worst conjunction
    worst = _worst_conjunction(list(ctx.conjunctions), _RISK_ORDER)
    if worst is None:
        return {
            "status": "no_action",
            "risk_level": final_risk,
            "message": "No conjunction data available.",
        }

    # Step 4: Propagate both objects to TCA
    our_state_at_tca = await propagator.propagate_to_time(ctx.tle, worst.tca)
    if our_state_at_tca is None:
        raise HTTPException(status_code=500, detail="SGP4 propagation failed for primary object")

    # Propagate threat object — requires its TLE
    threat_state_at_tca: StateVector | None = None
    try:
        threat_tle = await celestrak.get_tle(worst.secondary_norad_id)
        threat_state_at_tca = await propagator.propagate_to_time(threat_tle, worst.tca)
    except Exception as exc:
        logger.warning("Could not propagate threat object %d: %s", worst.secondary_norad_id, exc)

    # Build SpaceObjectPayloads
    our_obj = SpaceObjectPayload(
        object_id=str(norad_id),
        object_name=ctx.object_name,
        object_type="satellite",
        position_km=_state_to_eci(our_state_at_tca),
        velocity_km_s=_vel_to_eci(our_state_at_tca),
    )

    if threat_state_at_tca is not None:
        rel_vel = EciVector(
            x=threat_state_at_tca.vx_km_s - our_state_at_tca.vx_km_s,
            y=threat_state_at_tca.vy_km_s - our_state_at_tca.vy_km_s,
            z=threat_state_at_tca.vz_km_s - our_state_at_tca.vz_km_s,
        )
        threat_obj = SpaceObjectPayload(
            object_id=str(worst.secondary_norad_id),
            object_name=worst.secondary_object_name,
            object_type=_object_type_str(worst.secondary_object_type),
            position_km=_state_to_eci(threat_state_at_tca),
            velocity_km_s=_vel_to_eci(threat_state_at_tca),
        )
    else:
        # TLE unavailable — use relative speed as magnitude proxy on radial axis
        speed = worst.relative_speed_km_s or 7.5
        rel_vel = EciVector(x=speed, y=0.0, z=0.0)
        threat_obj = SpaceObjectPayload(
            object_id=str(worst.secondary_norad_id),
            object_name=worst.secondary_object_name,
            object_type=_object_type_str(worst.secondary_object_type),
            # Estimated from relative geometry: offset by miss distance in radial direction
            position_km=EciVector(
                x=our_state_at_tca.x_km + worst.miss_distance_km,
                y=our_state_at_tca.y_km,
                z=our_state_at_tca.z_km,
            ),
            velocity_km_s=EciVector(
                x=our_state_at_tca.vx_km_s + speed,
                y=our_state_at_tca.vy_km_s,
                z=our_state_at_tca.vz_km_s,
            ),
        )

    # Step 5: Build weather_parameters dict
    sw = ctx.space_weather
    weather_parameters = {
        "kp_index": sw.current_kp,
        "kp_24h_max": sw.kp_24h_max,
        "storm_level": sw.storm_level,
        "solar_flux_f10_7": sw.f107_obs,
        "f107_81day_avg": sw.f107_81day_avg,
        "ap_daily": sw.ap_daily,
        "atmospheric_drag_enhancement_factor": sw.atmospheric_drag_enhancement_factor,
        "active_alerts": sw.active_alerts,
    }

    # Step 6: Multi-threat awareness — all other high-risk conjunctions
    other_high_risk = [
        ConjunctionSummary(
            event_id=c.event_id,
            tca=c.tca,
            miss_distance_km=c.miss_distance_km,
            collision_probability=c.collision_probability,
            secondary_object_name=c.secondary_object_name,
            secondary_object_type=c.secondary_object_type,
        )
        for c in ctx.high_risk_conjunctions
        if c.event_id != worst.event_id
    ]

    # Step 7: Ground contact
    next_contact = ctx.upcoming_ground_contacts[0] if ctx.upcoming_ground_contacts else None
    if next_contact is not None:
        now = datetime.now(timezone.utc)
        minutes_to_contact = (next_contact.aos - now).total_seconds() / 60.0
    else:
        minutes_to_contact = None

    # Step 8: Atmospheric context
    atm = ctx.atmospheric_state
    atm_density = atm.total_mass_density_kg_m3 if atm else None
    atm_drag = atm.estimated_drag_acceleration_m_s2 if atm else None

    # Step 9: Determine rule_based and ml_risk from context
    # These are now embedded in the context as final risk — we surface them separately
    # by re-reading from the context builder's last run. For simplicity we use the
    # final risk for both and label it accordingly.
    rule_based_risk = final_risk
    ml_risk = final_risk  # The context already merged both; future: expose individually

    # Step 10: Assemble EnrichedCollisionAlert
    now_utc = datetime.now(timezone.utc)
    tca_seconds = (worst.tca - now_utc).total_seconds()

    alert = EnrichedCollisionAlert(
        alert_id=f"ECA-{worst.event_id}-{uuid.uuid4().hex[:8]}",
        generated_at=now_utc,
        cdm_source=worst.cdm_source,
        time_of_closest_approach=worst.tca,
        time_to_tca_seconds=max(tca_seconds, 0.0),
        miss_distance_m=worst.miss_distance_km * 1000.0,
        probability_of_collision=worst.collision_probability or 0.0,
        relative_velocity_km_s=rel_vel,
        our_object=our_obj,
        threat_object=threat_obj,
        threat_level=_RISK_TO_THREAT[final_risk],
        rule_based_risk=rule_based_risk,
        ml_risk=ml_risk,
        final_risk=final_risk,
        recommended_action=ctx.recommended_action,
        weather_parameters=weather_parameters,
        atmospheric_density_kg_m3=atm_density,
        atmospheric_drag_acceleration_m_s2=atm_drag,
        total_active_conjunctions=len(ctx.conjunctions),
        other_high_risk_conjunctions=other_high_risk,
        minutes_to_next_ground_contact=minutes_to_contact,
        next_ground_station_name=next_contact.ground_station_name if next_contact else None,
        data_freshness=ctx.data_freshness,
        raw_conjunction_data=worst.model_dump(mode="json"),
    )

    alert_dict = alert.model_dump(mode="json")

    # Step 11: POST to sentinel_agent
    sentinel_response: dict | None = None
    if settings.sentinel_agent_url:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{settings.sentinel_agent_url}/negotiate",
                    json=alert_dict,
                )
                resp.raise_for_status()
                sentinel_response = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("sentinel_agent unreachable: %s", exc)

    return {
        "status": "triggered" if sentinel_response is not None else "alert_only",
        "risk_level": final_risk,
        "alert": alert_dict,
        "negotiation_result": sentinel_response,
    }


@router.post("/satellites/{norad_id}/negotiate")
async def trigger_negotiation(
    norad_id: int,
    builder=Depends(_get_builder),
    celestrak=Depends(_get_celestrak),
    propagator=Depends(_get_propagator),
) -> dict:
    """
    Detect high-risk conjunctions for a satellite and trigger sentinel_agent negotiation.
    Delegates to run_negotiate_pipeline().
    """
    return await run_negotiate_pipeline(norad_id, builder, celestrak, propagator)
