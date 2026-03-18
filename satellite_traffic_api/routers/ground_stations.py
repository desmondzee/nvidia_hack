from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from satellite_traffic_api.models.ground_station import VisibilityWindow

router = APIRouter(tags=["ground_stations"])


@router.get("/satellites/{norad_id}/ground-contacts", response_model=list[VisibilityWindow])
async def get_ground_contacts(norad_id: int, request: Request) -> list[VisibilityWindow]:
    """Upcoming ground station contact windows for a satellite."""
    celestrak = request.app.state.celestrak
    ground_station = request.app.state.ground_station
    try:
        tle = await celestrak.get_tle(norad_id)
        return await ground_station.get_passes(tle)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
