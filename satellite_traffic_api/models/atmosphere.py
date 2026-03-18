from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AtmosphericState(BaseModel):
    model_config = ConfigDict(frozen=True)

    altitude_km: float
    latitude_deg: float
    longitude_deg: float
    timestamp: datetime
    total_mass_density_kg_m3: float
    exospheric_temperature_k: float
    local_temperature_k: float
    # Estimated drag acceleration (m/s^2) — None if satellite mass/area unknown
    estimated_drag_acceleration_m_s2: float | None = None
