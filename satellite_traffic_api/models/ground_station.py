from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class VisibilityWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    ground_station_name: str
    aos: datetime          # Acquisition of signal
    los: datetime          # Loss of signal
    max_elevation_deg: float
    duration_seconds: float
