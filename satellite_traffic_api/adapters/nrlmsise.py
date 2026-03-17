from __future__ import annotations
import asyncio
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from .base import BaseAdapter
from satellite_traffic_api.cache.backend import CacheBackend
from satellite_traffic_api.config import Settings
from satellite_traffic_api.models.atmosphere import AtmosphericState

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="nrlmsise")

# Default satellite ballistic coefficient (Cd * A / m) in m^2/kg
_DEFAULT_BC = 0.01


def _run_nrlmsise(
    alt_km: float,
    lat_deg: float,
    lon_deg: float,
    dt: datetime,
    f107: float,
    f107a: float,
    ap: float,
) -> dict:
    try:
        from nrlmsise00 import msise_model
        result = msise_model(dt, alt_km, lat_deg, lon_deg, f107a, f107, [ap] * 7)
        # result[0] = densities array, result[1] = temperatures
        d = result[0]   # [He, O, N2, O2, AR, total, H, N, anomO] in cm^-3 except total in g/cm^3
        t = result[1]   # [exospheric_T, local_T]
        total_density_g_cm3 = d[5]
        total_density_kg_m3 = total_density_g_cm3 * 1000  # g/cm^3 → kg/m^3
        exo_t = t[0]
        local_t = t[1]
    except ImportError:
        logger.warning("nrlmsise00 not installed; using exponential atmosphere fallback")
        # Exponential atmosphere fallback
        rho0 = 1.225  # kg/m^3 at sea level
        H = 8.5       # scale height km
        total_density_kg_m3 = rho0 * (2.718 ** (-(alt_km) / H)) * (1e-9)  # rough LEO scale
        exo_t = 1000.0
        local_t = 200.0

    # Estimate drag acceleration: a = 0.5 * rho * Cd * (A/m) * v^2
    # v ≈ 7.8 km/s for LEO
    v_m_s = 7800.0
    drag_accel = 0.5 * total_density_kg_m3 * 2.2 * _DEFAULT_BC * v_m_s**2

    return {
        "total_density_kg_m3": total_density_kg_m3,
        "exospheric_temperature_k": exo_t,
        "local_temperature_k": local_t,
        "drag_accel_m_s2": drag_accel,
    }


class NRLMSISEAdapter(BaseAdapter[AtmosphericState]):
    """Computes atmospheric density using NRLMSISE-00 (local computation, no HTTP)."""

    def __init__(self, settings: Settings, cache: CacheBackend) -> None:
        super().__init__(settings, cache)

    @property
    def ttl_seconds(self) -> int:
        return self.settings.cache_ttl_atmosphere_seconds

    def cache_key(self, **kwargs) -> str:
        # Quantize altitude to 1km, lat/lon to 1 degree, time to hour
        alt = round(kwargs.get("altitude_km", 0))
        lat = round(kwargs.get("latitude_deg", 0))
        lon = round(kwargs.get("longitude_deg", 0))
        dt: datetime = kwargs.get("timestamp", datetime.now(timezone.utc))
        epoch_h = int(dt.timestamp() / 3600)
        f107 = round(kwargs.get("f107", 150))
        ap = round(kwargs.get("ap", 10))
        key_str = f"{alt}:{lat}:{lon}:{epoch_h}:{f107}:{ap}"
        return f"nrlmsise:{hashlib.md5(key_str.encode()).hexdigest()[:12]}"

    async def fetch_raw(self, **kwargs) -> Any:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,
            _run_nrlmsise,
            kwargs.get("altitude_km", 400),
            kwargs.get("latitude_deg", 0),
            kwargs.get("longitude_deg", 0),
            kwargs.get("timestamp", datetime.now(timezone.utc)),
            kwargs.get("f107", 150.0),
            kwargs.get("f107a", 150.0),
            kwargs.get("ap", 10.0),
        )
        return {**result, **kwargs}

    def normalize(self, raw: Any, **kwargs) -> AtmosphericState:
        dt = raw.get("timestamp", datetime.now(timezone.utc))
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        return AtmosphericState(
            altitude_km=raw.get("altitude_km", 0),
            latitude_deg=raw.get("latitude_deg", 0),
            longitude_deg=raw.get("longitude_deg", 0),
            timestamp=dt,
            total_mass_density_kg_m3=raw.get("total_density_kg_m3", 0),
            exospheric_temperature_k=raw.get("exospheric_temperature_k", 0),
            local_temperature_k=raw.get("local_temperature_k", 0),
            estimated_drag_acceleration_m_s2=raw.get("drag_accel_m_s2"),
        )

    async def get_state(
        self,
        altitude_km: float,
        latitude_deg: float,
        longitude_deg: float,
        timestamp: datetime,
        f107: float = 150.0,
        f107a: float = 150.0,
        ap: float = 10.0,
    ) -> AtmosphericState:
        return await self.get(
            altitude_km=altitude_km,
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            timestamp=timestamp,
            f107=f107,
            f107a=f107a,
            ap=ap,
        )
