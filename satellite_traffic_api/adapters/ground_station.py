from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

from .base import BaseAdapter
from satellite_traffic_api.cache.backend import CacheBackend
from satellite_traffic_api.config import Settings
from satellite_traffic_api.models.ground_station import VisibilityWindow
from satellite_traffic_api.models.orbital import TLERecord

logger = logging.getLogger(__name__)


def _compute_passes(tle: TLERecord, gs_configs: list[dict], hours: int = 24) -> list[VisibilityWindow]:
    """Compute ground station visibility passes using skyfield."""
    try:
        from skyfield.api import EarthSatellite, Topos, load, wgs84
        ts = load.timescale()
    except ImportError:
        logger.warning("skyfield not installed; ground station passes unavailable")
        return []

    satellite = EarthSatellite(tle.line1, tle.line2, tle.object_name, ts)
    t0 = ts.now()
    t1 = ts.tt_jd(t0.tt + hours / 24.0)

    windows = []
    for gs in gs_configs:
        try:
            location = Topos(
                latitude_degrees=gs["lat"],
                longitude_degrees=gs["lon"],
                elevation_m=gs.get("elevation_m", 0),
            )
            min_elev = gs.get("min_elevation_deg", 5)
            times, events = satellite.find_events(location, t0, t1, altitude_degrees=min_elev)

            i = 0
            while i < len(events) - 1:
                if events[i] == 0:  # Rise
                    aos_t = times[i].utc_datetime()
                    # Find the corresponding set event
                    los_t = None
                    max_el = 0.0
                    for j in range(i + 1, len(events)):
                        if events[j] == 1:  # Culmination
                            diff = satellite - location
                            topocentric = diff.at(times[j])
                            el, _, _ = topocentric.altaz()
                            max_el = float(el.degrees)
                        elif events[j] == 2:  # Set
                            los_t = times[j].utc_datetime()
                            i = j
                            break
                    if los_t:
                        duration = (los_t - aos_t).total_seconds()
                        windows.append(VisibilityWindow(
                            ground_station_name=gs["name"],
                            aos=aos_t,
                            los=los_t,
                            max_elevation_deg=max_el,
                            duration_seconds=duration,
                        ))
                i += 1
        except Exception as exc:
            logger.warning("Pass computation failed for %s: %s", gs.get("name"), exc)

    return sorted(windows, key=lambda w: w.aos)


class GroundStationAdapter(BaseAdapter[list[VisibilityWindow]]):
    """Computes ground station visibility passes using skyfield (local computation)."""

    def __init__(self, settings: Settings, cache: CacheBackend) -> None:
        super().__init__(settings, cache)

    @property
    def ttl_seconds(self) -> int:
        return self.settings.cache_ttl_ground_contacts_seconds

    def cache_key(self, **kwargs) -> str:
        norad_id = kwargs.get("norad_id", 0)
        return f"groundstation:passes:{norad_id}"

    async def fetch_raw(self, **kwargs) -> Any:
        tle: TLERecord = kwargs["tle"]
        hours: int = kwargs.get("hours", 24)
        passes = _compute_passes(tle, self.settings.ground_stations, hours=hours)
        return [p.model_dump(mode="json") for p in passes]

    def normalize(self, raw: Any, **kwargs) -> list[VisibilityWindow]:
        return [VisibilityWindow(**p) for p in raw]

    async def get_passes(self, tle: TLERecord, hours: int = 24) -> list[VisibilityWindow]:
        key = self.cache_key(norad_id=tle.norad_cat_id)
        cached = await self.cache.get(key)
        if cached is not None:
            return self.normalize(cached)
        raw = await self.fetch_raw(tle=tle, hours=hours)
        await self.cache.set(key, raw, ttl=self.ttl_seconds)
        return self.normalize(raw)
