from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict


class KpIndexSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    time_tag: datetime
    kp_index: int
    estimated_kp: float


class SolarWindState(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    bx_gsm: float | None = None   # nT
    by_gsm: float | None = None
    bz_gsm: float | None = None
    bt: float | None = None
    plasma_density_cm3: float | None = None
    plasma_speed_km_s: float | None = None
    plasma_temperature_k: float | None = None


class SpaceWeatherSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    fetched_at: datetime
    current_kp: float
    kp_24h_max: float
    storm_level: Literal["NONE", "G1", "G2", "G3", "G4", "G5"]
    f107_obs: float              # Solar radio flux sfu
    f107_81day_avg: float
    ap_daily: float
    solar_wind: SolarWindState | None = None
    active_alerts: list[str] = []
    # Derived: 1.0 baseline, increases during geomagnetic storms
    atmospheric_drag_enhancement_factor: float = 1.0
