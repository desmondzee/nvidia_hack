from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
import httpx
from .base import BaseAdapter
from satellite_traffic_api.cache.backend import CacheBackend
from satellite_traffic_api.config import Settings
from satellite_traffic_api.models.space_weather import (
    SpaceWeatherSummary, KpIndexSample, SolarWindState
)

logger = logging.getLogger(__name__)

# NOAA SWPC endpoints
_KP_URL = "/json/planetary_k_index_1m.json"
_PLASMA_URL = "/products/solar-wind/plasma-5-minute.json"
_MAG_URL = "/products/solar-wind/mag-5-minute.json"
_ALERTS_URL = "/products/alerts.json"
_F107_URL = "/json/solar-cycle/observed-solar-cycle-indices.json"


def _kp_to_storm_level(kp: float) -> str:
    if kp >= 9: return "G5"
    if kp >= 8: return "G4"
    if kp >= 7: return "G3"
    if kp >= 6: return "G2"
    if kp >= 5: return "G1"
    return "NONE"


def _drag_enhancement(storm_level: str) -> float:
    return {"NONE": 1.0, "G1": 1.1, "G2": 1.2, "G3": 1.3, "G4": 1.4, "G5": 1.5}[storm_level]


def _parse_array_json(data: list) -> list[dict]:
    """NOAA returns [[header...], [row...], ...]. Convert to list of dicts."""
    if not data or not isinstance(data[0], list):
        return []
    headers = data[0]
    return [dict(zip(headers, row)) for row in data[1:]]


class NOAASpaceWeatherAdapter(BaseAdapter[SpaceWeatherSummary]):
    """Fetches space weather data from NOAA SWPC. No authentication required."""

    def __init__(self, settings: Settings, cache: CacheBackend, client: httpx.AsyncClient) -> None:
        super().__init__(settings, cache)
        self._client = client

    @property
    def ttl_seconds(self) -> int:
        return self.settings.cache_ttl_space_weather_seconds

    def cache_key(self, **kwargs) -> str:
        return "noaa:space_weather:summary"

    async def _get(self, path: str) -> Any:
        url = self.settings.noaa_swpc_base_url + path
        resp = await self._client.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()

    async def fetch_raw(self, **kwargs) -> dict:
        import asyncio
        kp_data, plasma_data, mag_data, alerts_data = await asyncio.gather(
            self._get(_KP_URL),
            self._get(_PLASMA_URL),
            self._get(_MAG_URL),
            self._get(_ALERTS_URL),
            return_exceptions=True,
        )
        return {
            "kp": kp_data if not isinstance(kp_data, Exception) else [],
            "plasma": plasma_data if not isinstance(plasma_data, Exception) else [],
            "mag": mag_data if not isinstance(mag_data, Exception) else [],
            "alerts": alerts_data if not isinstance(alerts_data, Exception) else [],
        }

    def normalize(self, raw: dict, **kwargs) -> SpaceWeatherSummary:
        now = datetime.now(timezone.utc)

        # Kp index
        kp_records = raw.get("kp", [])
        if isinstance(kp_records, list) and kp_records:
            # Already a list of dicts from NOAA
            valid_kp = [r for r in kp_records if isinstance(r, dict) and r.get("estimated_kp") is not None]
            current_kp = float(valid_kp[-1]["estimated_kp"]) if valid_kp else 0.0
            kp_24h_max = max((float(r["estimated_kp"]) for r in valid_kp), default=0.0)
        else:
            current_kp = 0.0
            kp_24h_max = 0.0

        storm_level = _kp_to_storm_level(current_kp)

        # Solar wind plasma
        plasma_rows = _parse_array_json(raw.get("plasma", []))
        solar_wind = None
        if plasma_rows:
            latest_plasma = plasma_rows[-1]
            mag_rows = _parse_array_json(raw.get("mag", []))
            latest_mag = mag_rows[-1] if mag_rows else {}
            try:
                solar_wind = SolarWindState(
                    timestamp=now,
                    bx_gsm=float(latest_mag.get("bx_gsm") or 0),
                    by_gsm=float(latest_mag.get("by_gsm") or 0),
                    bz_gsm=float(latest_mag.get("bz_gsm") or 0),
                    bt=float(latest_mag.get("bt") or 0),
                    plasma_density_cm3=float(latest_plasma.get("density") or 0),
                    plasma_speed_km_s=float(latest_plasma.get("speed") or 0),
                    plasma_temperature_k=float(latest_plasma.get("temperature") or 0),
                )
            except Exception as exc:
                logger.debug("Solar wind parse error: %s", exc)

        # Alerts
        alerts_raw = raw.get("alerts", [])
        active_alerts = []
        if isinstance(alerts_raw, list):
            for a in alerts_raw:
                if isinstance(a, dict):
                    msg = a.get("message", "")
                    if msg:
                        # First line only
                        active_alerts.append(msg.split("\n")[0][:120])

        return SpaceWeatherSummary(
            fetched_at=now,
            current_kp=current_kp,
            kp_24h_max=kp_24h_max,
            storm_level=storm_level,
            f107_obs=150.0,       # Placeholder; real value needs separate NOAA endpoint
            f107_81day_avg=150.0,
            ap_daily=max(0.0, (current_kp ** 2) * 2.5),  # Approximate Ap from Kp
            solar_wind=solar_wind,
            active_alerts=active_alerts[:5],
            atmospheric_drag_enhancement_factor=_drag_enhancement(storm_level),
        )

    async def get_summary(self) -> SpaceWeatherSummary:
        return await self.get()
