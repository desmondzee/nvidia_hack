from __future__ import annotations

import json
from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GroundStationConfig(dict):
    """Dict with keys: name, lat, lon, elevation_m, min_elevation_deg"""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Space-Track credentials
    space_track_user: str = ""
    space_track_password: str = ""

    # Base URLs
    celestrak_base_url: str = "https://celestrak.org"
    noaa_swpc_base_url: str = "https://services.swpc.noaa.gov"
    space_track_base_url: str = "https://www.space-track.org"

    # Redis
    redis_url: str = ""

    # Cache TTLs (seconds)
    cache_ttl_tle_seconds: int = 3600
    cache_ttl_conjunction_seconds: int = 1800
    cache_ttl_space_weather_seconds: int = 300
    cache_ttl_propagation_seconds: int = 60
    cache_ttl_ground_contacts_seconds: int = 1800
    cache_ttl_atmosphere_seconds: int = 3600

    # Propagation
    propagation_step_seconds: int = 60
    conjunction_lookahead_days: int = 7
    nearby_radius_km: float = 200.0

    # Ground stations
    ground_stations: list[dict[str, Any]] = [
        {"name": "Svalbard", "lat": 78.23, "lon": 15.40, "elevation_m": 458, "min_elevation_deg": 5},
        {"name": "McMurdo", "lat": -77.85, "lon": 166.67, "elevation_m": 10, "min_elevation_deg": 5},
        {"name": "Fairbanks", "lat": 64.86, "lon": -147.84, "elevation_m": 153, "min_elevation_deg": 5},
    ]

    @field_validator("ground_stations", mode="before")
    @classmethod
    def parse_ground_stations(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @property
    def has_space_track(self) -> bool:
        return bool(self.space_track_user and self.space_track_password)

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)


settings = Settings()
