from __future__ import annotations
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from sgp4.api import Satrec, jday

from .base import BaseAdapter
from satellite_traffic_api.cache.backend import CacheBackend
from satellite_traffic_api.config import Settings
from satellite_traffic_api.models.orbital import TLERecord, StateVector

logger = logging.getLogger(__name__)


def _propagate_to(sat: Satrec, dt: datetime) -> StateVector | None:
    """Propagate satellite to given datetime. Returns None on error."""
    jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond / 1e6)
    e, r, v = sat.sgp4(jd, fr)
    if e != 0:
        return None

    x, y, z = r
    vx, vy, vz = v
    speed = math.sqrt(vx**2 + vy**2 + vz**2)

    # ECI → geodetic (simplified spherical approximation)
    r_mag = math.sqrt(x**2 + y**2 + z**2)
    lat = math.degrees(math.asin(z / r_mag))
    lon = math.degrees(math.atan2(y, x))
    # Account for Earth's rotation (GMST approximation)
    # Julian date → GMST in degrees
    jd_full = jd + fr
    t_ut1 = (jd_full - 2451545.0) / 36525.0
    gmst = (280.46061837 + 360.98564736629 * (jd_full - 2451545.0)
            + 0.000387933 * t_ut1**2) % 360
    lon = (lon - gmst + 180) % 360 - 180
    alt = r_mag - 6371.0  # Earth radius km

    return StateVector(
        timestamp=dt,
        x_km=x, y_km=y, z_km=z,
        vx_km_s=vx, vy_km_s=vy, vz_km_s=vz,
        latitude_deg=lat,
        longitude_deg=lon,
        altitude_km=alt,
        speed_km_s=speed,
    )


class PropagatorAdapter(BaseAdapter[StateVector]):
    """Propagates satellite orbits using SGP4."""

    def __init__(self, settings: Settings, cache: CacheBackend) -> None:
        super().__init__(settings, cache)

    @property
    def ttl_seconds(self) -> int:
        return self.settings.cache_ttl_propagation_seconds

    def cache_key(self, **kwargs) -> str:
        norad_id = kwargs.get("norad_id", 0)
        epoch_min = kwargs.get("epoch_min", 0)
        return f"propagator:state:{norad_id}:{epoch_min}"

    async def fetch_raw(self, **kwargs) -> Any:
        # No external fetch — computation is local
        return kwargs

    def normalize(self, raw: Any, **kwargs) -> StateVector:
        return raw  # Already a StateVector when called via get_current_state

    async def get_current_state(self, tle: TLERecord) -> StateVector:
        now = datetime.now(timezone.utc)
        epoch_min = int(now.timestamp() / 60)
        key = self.cache_key(norad_id=tle.norad_cat_id, epoch_min=epoch_min)

        cached = await self.cache.get(key)
        if cached is not None:
            return StateVector(**cached)

        sat = Satrec.twoline2rv(tle.line1, tle.line2)
        state = _propagate_to(sat, now)
        if state is None:
            raise ValueError(f"SGP4 propagation error for NORAD {tle.norad_cat_id}")

        await self.cache.set(key, state.model_dump(mode="json"), ttl=self.ttl_seconds)
        return state

    async def get_trajectory(self, tle: TLERecord, hours: int = 24) -> list[StateVector]:
        """Return hourly state vectors for the next N hours."""
        sat = Satrec.twoline2rv(tle.line1, tle.line2)
        now = datetime.now(timezone.utc)
        states = []
        for h in range(hours + 1):
            dt = now + timedelta(hours=h)
            state = _propagate_to(sat, dt)
            if state:
                states.append(state)
        return states

    async def propagate_to_time(self, tle: TLERecord, dt: datetime) -> StateVector | None:
        """Propagate satellite to an arbitrary datetime (e.g. TCA for conjunction mapping)."""
        sat = Satrec.twoline2rv(tle.line1, tle.line2)
        return _propagate_to(sat, dt)

    async def get_nearby(
        self, tle: TLERecord, catalog: list[TLERecord], radius_km: float | None = None
    ) -> list[TLERecord]:
        """Return TLERecords within radius_km of the satellite at current time."""
        if radius_km is None:
            radius_km = self.settings.nearby_radius_km

        sat = Satrec.twoline2rv(tle.line1, tle.line2)
        now = datetime.now(timezone.utc)
        own_state = _propagate_to(sat, now)
        if own_state is None:
            return []

        own_pos = np.array([own_state.x_km, own_state.y_km, own_state.z_km])
        nearby = []

        for other in catalog:
            if other.norad_cat_id == tle.norad_cat_id:
                continue
            try:
                other_sat = Satrec.twoline2rv(other.line1, other.line2)
                other_state = _propagate_to(other_sat, now)
                if other_state is None:
                    continue
                other_pos = np.array([other_state.x_km, other_state.y_km, other_state.z_km])
                dist = float(np.linalg.norm(own_pos - other_pos))
                if dist <= radius_km:
                    nearby.append(other)
            except Exception:
                continue

        return nearby
