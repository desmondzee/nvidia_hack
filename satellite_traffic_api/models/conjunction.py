from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict


class ConjunctionEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    tca: datetime                        # Time of closest approach
    miss_distance_km: float
    collision_probability: float | None = None
    relative_speed_km_s: float | None = None
    primary_norad_id: int
    secondary_norad_id: int
    secondary_object_name: str
    secondary_object_type: Literal["PAYLOAD", "DEBRIS", "ROCKET_BODY", "UNKNOWN"] = "UNKNOWN"
    cdm_source: Literal["CELESTRAK", "SPACETRACK"] = "SPACETRACK"
    days_until_tca: float
