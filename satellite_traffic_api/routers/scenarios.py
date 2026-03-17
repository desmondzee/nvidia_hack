from __future__ import annotations
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request, Response
from satellite_traffic_api.models.context import SatelliteContext
from satellite_traffic_api.models.conjunction import ConjunctionEvent
from satellite_traffic_api.scenarios.loader import load_scenario, get_scenario_step

router = APIRouter(tags=["scenarios"])


def _build_context_from_step(base_ctx: SatelliteContext, step_data: dict) -> SatelliteContext:
    """Overlay synthetic scenario data onto a real satellite context."""
    now = datetime.now(timezone.utc)
    s = step_data["current_step"]
    risk = s["risk_level"]
    tca = now + timedelta(minutes=s["tca_minutes_from_now"])

    # Build synthetic conjunction if threat is active
    conjunctions = []
    high_risk = []
    if s["miss_distance_km"] < 5.0:
        secondary = step_data["satellites"]["secondary"]
        conj = ConjunctionEvent(
            event_id=f"demo_{s['step']}",
            tca=tca,
            miss_distance_km=s["miss_distance_km"],
            collision_probability=s.get("collision_probability"),
            relative_speed_km_s=s.get("relative_speed_km_s"),
            primary_norad_id=base_ctx.norad_cat_id,
            secondary_norad_id=secondary["norad_id"],
            secondary_object_name=secondary["name"],
            secondary_object_type="PAYLOAD",
            cdm_source="SPACETRACK",
            days_until_tca=s["tca_minutes_from_now"] / 1440,
        )
        conjunctions = [conj]
        if s["miss_distance_km"] < 1.0 or (s.get("collision_probability") or 0) > 1e-4:
            high_risk = [conj]

    return SatelliteContext(
        **{
            **base_ctx.model_dump(),
            "conjunctions": conjunctions,
            "high_risk_conjunctions": high_risk,
            "collision_risk_level": risk,
            "recommended_action": s["recommended_action"],
            "extensions": {
                "scenario_id": step_data["scenario_id"],
                "scenario_step": s["step"],
                "scenario_label": s["label"],
                "narrative": s["narrative"],
            },
        }
    )


@router.get("/scenarios/{scenario_id}/step/{step}")
async def get_scenario_step_context(
    scenario_id: str,
    step: int,
    request: Request,
    response: Response,
) -> dict:
    """
    Returns the satellite context for a specific demo scenario step.
    Fetches real orbital + space weather data, overlays synthetic conjunction.
    """
    try:
        step_data = get_scenario_step(scenario_id, step)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    primary_norad = step_data["satellites"]["primary"]["norad_id"]
    builder = request.app.state.context_builder

    try:
        base_ctx = await builder.build(primary_norad)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    ctx = _build_context_from_step(base_ctx, step_data)
    response.headers["X-Risk-Level"] = ctx.collision_risk_level
    response.headers["X-Scenario-Step"] = str(step)
    return ctx.model_dump(mode="json")



@router.get("/scenarios/{scenario_id}")
async def get_scenario_info(scenario_id: str) -> dict:
    """Returns scenario metadata and available steps."""
    try:
        scenario = load_scenario(scenario_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "scenario_id": scenario_id,
        "description": scenario.get("description"),
        "satellites": scenario.get("satellites"),
        "steps": [
            {"step": s["step"], "label": s["label"], "risk_level": s["risk_level"]}
            for s in scenario.get("steps", [])
        ],
        "generated_at": scenario.get("generated_at"),
    }
