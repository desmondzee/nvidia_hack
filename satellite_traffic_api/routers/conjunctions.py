from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from satellite_traffic_api.models.conjunction import ConjunctionEvent

router = APIRouter(tags=["conjunctions"])


@router.get("/satellites/{norad_id}/conjunctions", response_model=list[ConjunctionEvent])
async def get_conjunctions(norad_id: int, request: Request) -> list[ConjunctionEvent]:
    """
    Predicted close approaches for a satellite.
    Requires SPACE_TRACK_USER and SPACE_TRACK_PASSWORD to be configured.
    """
    spacetrack = request.app.state.spacetrack
    if spacetrack is None:
        raise HTTPException(
            status_code=503,
            detail="Space-Track credentials not configured. Set SPACE_TRACK_USER and SPACE_TRACK_PASSWORD.",
        )
    try:
        return await spacetrack.get_conjunctions(norad_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
