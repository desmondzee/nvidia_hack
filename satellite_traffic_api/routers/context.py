from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from satellite_traffic_api.models.context import SatelliteContext

router = APIRouter(tags=["context"])


def get_builder(request: Request):
    return request.app.state.context_builder


@router.get("/satellites/{norad_id}/context", response_model=SatelliteContext)
async def get_satellite_context(
    norad_id: int,
    response: Response,
    builder=Depends(get_builder),
) -> SatelliteContext:
    """
    Primary agent endpoint. Returns full situational context for a satellite.
    Includes orbital state, conjunctions, space weather, atmosphere, ground contacts.
    """
    try:
        ctx = await builder.build(norad_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    response.headers["X-Context-Expires"] = ctx.context_valid_until.isoformat()
    response.headers["X-Risk-Level"] = ctx.collision_risk_level
    return ctx
