from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
import httpx
from .base import BaseAdapter
from satellite_traffic_api.cache.backend import CacheBackend
from satellite_traffic_api.config import Settings
from satellite_traffic_api.models.conjunction import ConjunctionEvent

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://www.space-track.org/ajaxauth/login"
_BASE = "https://www.space-track.org/basicspacedata/query/class"


def _object_type(name: str) -> str:
    name_upper = name.upper()
    if "DEB" in name_upper:
        return "DEBRIS"
    if "R/B" in name_upper or "ROCKET" in name_upper:
        return "ROCKET_BODY"
    return "PAYLOAD"


class SpaceTrackAdapter(BaseAdapter[list[ConjunctionEvent]]):
    """
    Fetches conjunction data messages (CDMs) from Space-Track.org.
    Requires SPACE_TRACK_USER and SPACE_TRACK_PASSWORD in settings.
    """

    def __init__(self, settings: Settings, cache: CacheBackend, client: httpx.AsyncClient) -> None:
        super().__init__(settings, cache)
        self._client = client
        self._authenticated = False
        self._auth_lock = asyncio.Lock()
        # Simple rate limiter: max 20 req/min
        self._request_times: list[float] = []

    @property
    def ttl_seconds(self) -> int:
        return self.settings.cache_ttl_conjunction_seconds

    def cache_key(self, **kwargs) -> str:
        return f"spacetrack:cdm:{kwargs.get('norad_id')}"

    async def _ensure_authenticated(self) -> None:
        async with self._auth_lock:
            if self._authenticated:
                return
            if not self.settings.has_space_track:
                raise RuntimeError(
                    "Space-Track credentials not configured. "
                    "Set SPACE_TRACK_USER and SPACE_TRACK_PASSWORD in .env"
                )
            resp = await self._client.post(
                _LOGIN_URL,
                data={"identity": self.settings.space_track_user,
                      "password": self.settings.space_track_password},
                timeout=15,
            )
            resp.raise_for_status()
            self._authenticated = True
            logger.info("Authenticated with Space-Track.org")

    async def _rate_limited_get(self, url: str, **kwargs) -> httpx.Response:
        """Enforce max 20 requests/minute."""
        now = time.monotonic()
        self._request_times = [t for t in self._request_times if now - t < 60]
        if len(self._request_times) >= 20:
            wait = 60 - (now - self._request_times[0]) + 0.1
            logger.warning("Space-Track rate limit reached, waiting %.1fs", wait)
            await asyncio.sleep(wait)
        self._request_times.append(time.monotonic())
        return await self._client.get(url, **kwargs)

    async def fetch_raw(self, **kwargs) -> Any:
        norad_id = kwargs["norad_id"]
        await self._ensure_authenticated()

        now = datetime.now(timezone.utc)
        future = now + timedelta(days=self.settings.conjunction_lookahead_days)
        tca_start = now.strftime("%Y-%m-%d")
        tca_end = future.strftime("%Y-%m-%d")

        # Query CDMs where this satellite is SAT1 or SAT2
        url = (
            f"{_BASE}/cdm/TCA/%3E{tca_start}/TCA/%3C{tca_end}"
            f"/NORAD_CAT_ID_1/{norad_id}/format/json/orderby/TCA%20asc"
        )
        resp = await self._rate_limited_get(url, timeout=30)
        if resp.status_code == 401:
            self._authenticated = False
            await self._ensure_authenticated()
            resp = await self._rate_limited_get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def normalize(self, raw: Any, **kwargs) -> list[ConjunctionEvent]:
        norad_id = kwargs.get("norad_id", 0)
        now = datetime.now(timezone.utc)
        events = []
        if not isinstance(raw, list):
            return events

        for rec in raw:
            try:
                tca_str = rec.get("TCA", "")
                tca = datetime.fromisoformat(tca_str.replace("Z", "+00:00"))
                days_until = (tca - now).total_seconds() / 86400

                miss_dist = rec.get("MISS_DISTANCE")
                if miss_dist is None:
                    continue

                prob_raw = rec.get("COLLISION_PROBABILITY")
                prob = float(prob_raw) if prob_raw not in (None, "", "N/A") else None

                rel_speed = rec.get("RELATIVE_SPEED")

                sat2_id = int(rec.get("SAT2_ID") or rec.get("NORAD_CAT_ID_2") or 0)
                sat2_name = rec.get("SAT2_NAME") or rec.get("OBJECT_NAME_2") or "UNKNOWN"

                events.append(ConjunctionEvent(
                    event_id=rec.get("CDM_ID", f"{norad_id}_{sat2_id}_{tca_str}"),
                    tca=tca,
                    miss_distance_km=float(miss_dist),
                    collision_probability=prob,
                    relative_speed_km_s=float(rel_speed) if rel_speed else None,
                    primary_norad_id=norad_id,
                    secondary_norad_id=sat2_id,
                    secondary_object_name=sat2_name,
                    secondary_object_type=_object_type(sat2_name),
                    cdm_source="SPACETRACK",
                    days_until_tca=days_until,
                ))
            except Exception as exc:
                logger.warning("Failed to parse CDM record: %s — %s", rec, exc)

        return events

    async def get_conjunctions(self, norad_id: int) -> list[ConjunctionEvent]:
        return await self.get(norad_id=norad_id)
