from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from satellite_traffic_api.models.space_weather import SpaceWeatherSummary

router = APIRouter(tags=["space_weather"])


@router.get("/space-weather/current", response_model=SpaceWeatherSummary)
async def get_space_weather(request: Request) -> SpaceWeatherSummary:
    """Current space weather: Kp index, solar wind, geomagnetic storm level."""
    noaa = request.app.state.noaa
    try:
        return await noaa.get_summary()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
