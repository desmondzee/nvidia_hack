from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from satellite_traffic_api.models.context import SatelliteContext, RiskLevel
from satellite_traffic_api.models.conjunction import ConjunctionEvent
from satellite_traffic_api.models.space_weather import SpaceWeatherSummary

if TYPE_CHECKING:
    from satellite_traffic_api.adapters.celestrak import CelesTrakAdapter
    from satellite_traffic_api.adapters.spacetrack import SpaceTrackAdapter
    from satellite_traffic_api.adapters.noaa_space_weather import NOAASpaceWeatherAdapter
    from satellite_traffic_api.adapters.propagator import PropagatorAdapter
    from satellite_traffic_api.adapters.nrlmsise import NRLMSISEAdapter
    from satellite_traffic_api.adapters.ground_station import GroundStationAdapter

logger = logging.getLogger(__name__)


def _compute_risk(
    conjunctions: list[ConjunctionEvent],
    space_weather: SpaceWeatherSummary,
) -> RiskLevel:
    for c in conjunctions:
        if c.miss_distance_km < 0.2 or (c.collision_probability or 0) > 1e-3:
            return "CRITICAL"
    for c in conjunctions:
        if c.miss_distance_km < 1.0 or (c.collision_probability or 0) > 1e-4:
            return "HIGH"
    for c in conjunctions:
        if c.miss_distance_km < 5.0:
            return "ELEVATED"
    if space_weather.current_kp >= 7:
        return "ELEVATED"
    return "NOMINAL"


def _recommended_action(risk: RiskLevel, conjunctions: list[ConjunctionEvent]) -> str:
    if risk == "CRITICAL":
        closest = conjunctions[0] if conjunctions else None
        if closest:
            return (
                f"CRITICAL: Conjunction with {closest.secondary_object_name} "
                f"in {closest.days_until_tca:.2f} days at {closest.miss_distance_km:.3f} km. "
                "Initiate collision avoidance maneuver planning immediately."
            )
        return "CRITICAL risk level. Immediate assessment required."
    if risk == "HIGH":
        return "HIGH conjunction risk. Monitor closely and prepare contingency maneuver."
    if risk == "ELEVATED":
        return "ELEVATED risk. Continue monitoring. No immediate action required."
    return "NOMINAL. No action required."


class SatelliteContextBuilder:
    def __init__(
        self,
        celestrak: "CelesTrakAdapter",
        spacetrack: "SpaceTrackAdapter | None",
        noaa: "NOAASpaceWeatherAdapter",
        propagator: "PropagatorAdapter",
        nrlmsise: "NRLMSISEAdapter",
        ground_station: "GroundStationAdapter",
    ) -> None:
        self.celestrak = celestrak
        self.spacetrack = spacetrack
        self.noaa = noaa
        self.propagator = propagator
        self.nrlmsise = nrlmsise
        self.ground_station = ground_station

    async def build(self, norad_id: int) -> SatelliteContext:
        now = datetime.now(timezone.utc)
        freshness: dict[str, str] = {}

        # Step 1: Fetch TLE (required as input to all other adapters)
        tle = await self.celestrak.get_tle(norad_id)
        freshness["celestrak_tle"] = now.isoformat()

        # Step 2: Fan out all independent fetches concurrently
        conjunction_task = (
            self.spacetrack.get_conjunctions(norad_id)
            if self.spacetrack
            else asyncio.sleep(0, result=[])
        )

        current_state, space_weather, conjunctions, ground_contacts = await asyncio.gather(
            self.propagator.get_current_state(tle),
            self.noaa.get_summary(),
            conjunction_task,
            self.ground_station.get_passes(tle),
        )
        freshness["propagator"] = now.isoformat()
        freshness["noaa_space_weather"] = now.isoformat()
        if self.spacetrack:
            freshness["spacetrack_cdm"] = now.isoformat()

        # Step 3: Atmospheric state depends on current position + space weather
        atm_state = await self.nrlmsise.get_state(
            altitude_km=current_state.altitude_km,
            latitude_deg=current_state.latitude_deg,
            longitude_deg=current_state.longitude_deg,
            timestamp=current_state.timestamp,
            f107=space_weather.f107_obs,
            f107a=space_weather.f107_81day_avg,
            ap=space_weather.ap_daily,
        )
        freshness["nrlmsise_atmosphere"] = now.isoformat()

        # Step 4: Trajectory + nearby objects
        trajectory, active_catalog = await asyncio.gather(
            self.propagator.get_trajectory(tle, hours=24),
            self.celestrak.get_active_catalog(),
        )
        nearby = await self.propagator.get_nearby(tle, active_catalog)

        # Step 5: Assemble
        risk = _compute_risk(conjunctions, space_weather)
        high_risk = [
            c for c in conjunctions
            if c.miss_distance_km < 1.0 or (c.collision_probability or 0) > 1e-4
        ]

        valid_until = now + timedelta(seconds=60)  # Conservative: min TTL

        return SatelliteContext(
            norad_cat_id=norad_id,
            object_name=tle.object_name,
            fetched_at=now,
            context_valid_until=valid_until,
            tle=tle,
            current_state=current_state,
            orbit_next_24h=trajectory,
            conjunctions=sorted(conjunctions, key=lambda c: c.tca),
            high_risk_conjunctions=high_risk,
            space_weather=space_weather,
            atmospheric_state=atm_state,
            upcoming_ground_contacts=ground_contacts,
            nearby_object_ids=[o.norad_cat_id for o in nearby],
            nearby_object_names=[o.object_name for o in nearby],
            collision_risk_level=risk,
            recommended_action=_recommended_action(risk, sorted(conjunctions, key=lambda c: c.tca)),
            data_freshness=freshness,
        )
