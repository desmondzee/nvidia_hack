from __future__ import annotations
import logging
import math
from datetime import datetime, timezone
from typing import Any
import httpx
from sgp4.api import Satrec
from .base import BaseAdapter
from satellite_traffic_api.cache.backend import CacheBackend
from satellite_traffic_api.config import Settings
from satellite_traffic_api.models.orbital import TLERecord

logger = logging.getLogger(__name__)


def _parse_tle_text(text: str) -> list[TLERecord]:
    """Parse a multi-TLE text block (3-line format) into TLERecords."""
    records = []
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        # Each group: name, line1, line2
        if i + 2 >= len(lines) and not (lines[i].startswith("1 ") or lines[i].startswith("2 ")):
            break
        # Name line (not starting with 1 or 2)
        if not lines[i].startswith("1 ") and not lines[i].startswith("2 "):
            name = lines[i]
            line1 = lines[i + 1] if i + 1 < len(lines) else ""
            line2 = lines[i + 2] if i + 2 < len(lines) else ""
            i += 3
        else:
            name = "UNKNOWN"
            line1 = lines[i]
            line2 = lines[i + 1] if i + 1 < len(lines) else ""
            i += 2

        if not line1.startswith("1 ") or not line2.startswith("2 "):
            continue

        try:
            sat = Satrec.twoline2rv(line1, line2)
            # Convert sgp4 epoch (days from 1949-12-31) to datetime
            jd = sat.jdsatepoch + sat.jdsatepochF
            epoch = datetime.fromtimestamp((jd - 2440587.5) * 86400, tz=timezone.utc)

            records.append(TLERecord(
                norad_cat_id=sat.satnum,
                object_name=name.strip(),
                object_id="",
                epoch=epoch,
                mean_motion=sat.no_kozai * (1440 / (2 * math.pi)),  # rad/min → rev/day
                eccentricity=sat.ecco,
                inclination_deg=math.degrees(sat.inclo),
                raan_deg=math.degrees(sat.nodeo),
                arg_of_perigee_deg=math.degrees(sat.argpo),
                mean_anomaly_deg=math.degrees(sat.mo),
                bstar=sat.bstar,
                mean_motion_dot=sat.ndot,
                mean_motion_ddot=sat.nddot,
                element_set_no=sat.elnum,
                rev_at_epoch=sat.revnum,
                line1=line1,
                line2=line2,
            ))
        except Exception as exc:
            logger.debug("Failed to parse TLE for %s: %s", name, exc)

    return records


class CelesTrakAdapter(BaseAdapter[TLERecord]):
    """Fetches TLE data from CelesTrak. No authentication required."""

    def __init__(self, settings: Settings, cache: CacheBackend, client: httpx.AsyncClient) -> None:
        super().__init__(settings, cache)
        self._client = client

    @property
    def ttl_seconds(self) -> int:
        return self.settings.cache_ttl_tle_seconds

    def cache_key(self, **kwargs) -> str:
        norad_id = kwargs.get("norad_id")
        if norad_id:
            return f"celestrak:tle:norad:{norad_id}"
        return "celestrak:tle:group:active"

    async def fetch_raw(self, **kwargs) -> Any:
        norad_id = kwargs.get("norad_id")
        url = f"{self.settings.celestrak_base_url}/NORAD/elements/gp.php"
        params = {"CATNR": norad_id, "FORMAT": "TLE"} if norad_id else {"GROUP": "active", "FORMAT": "TLE"}

        logger.debug("CelesTrak fetch: %s %s", url, params)
        resp = await self._client.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.text  # TLE format is plain text

    def normalize(self, raw: Any, **kwargs) -> TLERecord | list[TLERecord]:
        norad_id = kwargs.get("norad_id")
        records = _parse_tle_text(raw)
        if norad_id:
            return records[0] if records else None
        return records

    async def get_tle(self, norad_id: int) -> TLERecord:
        return await self.get(norad_id=norad_id)

    async def get_active_catalog(self) -> list[TLERecord]:
        key = self.cache_key()
        cached = await self.cache.get(key)
        if cached is not None:
            return self.normalize(cached)
        raw = await self.fetch_raw()
        await self.cache.set(key, raw, ttl=self.ttl_seconds)
        return self.normalize(raw)
