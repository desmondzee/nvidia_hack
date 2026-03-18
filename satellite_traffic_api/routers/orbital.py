from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from satellite_traffic_api.models.orbital import TLERecord, StateVector

router = APIRouter(tags=["orbital"])


@router.get("/satellites/{norad_id}/tle", response_model=TLERecord)
async def get_tle(norad_id: int, request: Request) -> TLERecord:
    """Current TLE for a satellite."""
    celestrak = request.app.state.celestrak
    try:
        return await celestrak.get_tle(norad_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/satellites/{norad_id}/state", response_model=StateVector)
async def get_state(norad_id: int, request: Request) -> StateVector:
    """Current propagated state vector (position + velocity)."""
    celestrak = request.app.state.celestrak
    propagator = request.app.state.propagator
    try:
        tle = await celestrak.get_tle(norad_id)
        return await propagator.get_current_state(tle)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
