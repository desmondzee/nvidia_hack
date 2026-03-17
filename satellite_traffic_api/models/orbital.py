from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TLERecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    norad_cat_id: int
    object_name: str
    object_id: str = ""          # International designator e.g. "1998-067A"
    epoch: datetime
    mean_motion: float           # rev/day
    eccentricity: float
    inclination_deg: float
    raan_deg: float              # Right ascension of ascending node
    arg_of_perigee_deg: float
    mean_anomaly_deg: float
    bstar: float                 # Drag term
    mean_motion_dot: float
    mean_motion_ddot: float
    element_set_no: int = 0
    rev_at_epoch: int = 0
    line1: str
    line2: str


class StateVector(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    # ECI position (km)
    x_km: float
    y_km: float
    z_km: float
    # ECI velocity (km/s)
    vx_km_s: float
    vy_km_s: float
    vz_km_s: float
    # Geodetic
    latitude_deg: float
    longitude_deg: float
    altitude_km: float
    speed_km_s: float


class PropagatedOrbit(BaseModel):
    model_config = ConfigDict(frozen=True)

    norad_cat_id: int
    reference_epoch: datetime
    current_state: StateVector
    states_next_24h: list[StateVector]  # Hourly snapshots
