from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
import httpx
from .base import BaseAdapter
from satellite_traffic_api.cache.backend import CacheBackend
from satellite_traffic_api.config import Settings
from satellite_traffic_api.models.orbital import TLERecord

logger = logging.getLogger(__name__)


def _parse_gp_record(rec: dict) -> TLERecord:
    """Parse a CelesTrak GP JSON record into a TLERecord."""
    epoch_str = rec.get("EPOCH", "")
    try:
        epoch = datetime.fromisoformat(epoch_str.replace("Z", "+00:00"))
    except Exception:
        epoch = datetime.now(timezone.utc)

    return TLERecord(
        norad_cat_id=int(rec.get("NORAD_CAT_ID", 0)),
        object_name=rec.get("OBJECT_NAME", "UNKNOWN").strip(),
        object_id=rec.get("OBJECT_ID", ""),
        epoch=epoch,
        mean_motion=float(rec.get("MEAN_MOTION", 0)),
        eccentricity=float(rec.get("ECCENTRICITY", 0)),
        inclination_deg=float(rec.get("INCLINATION", 0)),
        raan_deg=float(rec.get("RA_OF_ASC_NODE", 0)),
        arg_of_perigee_deg=float(rec.get("ARG_OF_PERICENTER", 0)),
        mean_anomaly_deg=float(rec.get("MEAN_ANOMALY", 0)),
        bstar=float(rec.get("BSTAR", 0)),
        mean_motion_dot=float(rec.get("MEAN_MOTION_DOT", 0)),
        mean_motion_ddot=float(rec.get("MEAN_MOTION_DDOT", 0)),
        element_set_no=int(rec.get("ELEMENT_SET_NO", 0)),
        rev_at_epoch=int(rec.get("REV_AT_EPOCH", 0)),
        line1=rec.get("TLE_LINE1", ""),
        line2=rec.get("TLE_LINE2", ""),
    )


class CelesTrakAdapter(BaseAdapter[TLERecord]):
    """Fetches TLE/GP data from CelesTrak. No authentication required."""

    def __init__(self, settings: Settings, cache: CacheBackend, client: httpx.AsyncClient) -> None:
        super().__init__(settings, cache)
        self._client = client

    @property
    def ttl_seconds(self) -> int:
        return self.settings.cache_ttl_tle_seconds

    def cache_key(self, **kwargs) -> str:
        norad_id = kwargs.get("norad_id")
        if norad_id:
            return f"celestrak:gp:norad:{norad_id}"
        return "celestrak:gp:group:active"

    async def fetch_raw(self, **kwargs) -> Any:
        norad_id = kwargs.get("norad_id")
        if norad_id:
            url = f"{self.settings.celestrak_base_url}/NORAD/elements/gp.php"
            params = {"CATNR": norad_id, "FORMAT": "JSON"}
        else:
            url = f"{self.settings.celestrak_base_url}/NORAD/elements/gp.php"
            params = {"GROUP": "active", "FORMAT": "JSON"}

        logger.debug("CelesTrak fetch: %s %s", url, params)
        resp = await self._client.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def normalize(self, raw: Any, **kwargs) -> TLERecord | list[TLERecord]:
        norad_id = kwargs.get("norad_id")
        if not isinstance(raw, list):
            raw = [raw]
        records = [_parse_gp_record(r) for r in raw]
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
