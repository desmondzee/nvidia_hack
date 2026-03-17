from __future__ import annotations
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from satellite_traffic_api.config import settings
from satellite_traffic_api.cache.memory_backend import MemoryCacheBackend
from satellite_traffic_api.adapters.celestrak import CelesTrakAdapter
from satellite_traffic_api.adapters.spacetrack import SpaceTrackAdapter
from satellite_traffic_api.adapters.noaa_space_weather import NOAASpaceWeatherAdapter
from satellite_traffic_api.adapters.propagator import PropagatorAdapter
from satellite_traffic_api.adapters.nrlmsise import NRLMSISEAdapter
from satellite_traffic_api.adapters.ground_station import GroundStationAdapter
from satellite_traffic_api.aggregator.context_builder import SatelliteContextBuilder
from satellite_traffic_api.routers import context, orbital, conjunctions, space_weather, ground_stations

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # Cache backend
    if settings.has_redis:
        try:
            from satellite_traffic_api.cache.redis_backend import RedisCacheBackend
            cache = RedisCacheBackend(settings.redis_url)
            logger.info("Using Redis cache: %s", settings.redis_url)
        except Exception as exc:
            logger.warning("Redis unavailable (%s), falling back to in-memory cache", exc)
            cache = MemoryCacheBackend()
    else:
        logger.info("No REDIS_URL configured — using in-memory cache")
        cache = MemoryCacheBackend()

    # Shared HTTP client
    http_client = httpx.AsyncClient(
        headers={"User-Agent": "SatelliteTrafficAPI/1.0"},
        follow_redirects=True,
    )

    # Adapters
    celestrak = CelesTrakAdapter(settings, cache, http_client)
    noaa = NOAASpaceWeatherAdapter(settings, cache, http_client)
    propagator = PropagatorAdapter(settings, cache)
    nrlmsise = NRLMSISEAdapter(settings, cache)
    ground_station = GroundStationAdapter(settings, cache)

    spacetrack = None
    if settings.has_space_track:
        spacetrack = SpaceTrackAdapter(settings, cache, http_client)
        logger.info("Space-Track adapter enabled for user: %s", settings.space_track_user)
    else:
        logger.warning(
            "Space-Track credentials not set — conjunction data will be unavailable. "
            "Set SPACE_TRACK_USER and SPACE_TRACK_PASSWORD in .env"
        )

    # Context builder
    builder = SatelliteContextBuilder(
        celestrak=celestrak,
        spacetrack=spacetrack,
        noaa=noaa,
        propagator=propagator,
        nrlmsise=nrlmsise,
        ground_station=ground_station,
    )

    # Attach to app state
    app.state.cache = cache
    app.state.celestrak = celestrak
    app.state.spacetrack = spacetrack
    app.state.noaa = noaa
    app.state.propagator = propagator
    app.state.nrlmsise = nrlmsise
    app.state.ground_station = ground_station
    app.state.context_builder = builder

    logger.info("Satellite Traffic API started")
    yield

    # --- Shutdown ---
    await http_client.aclose()
    await cache.close()
    logger.info("Satellite Traffic API shut down")


app = FastAPI(
    title="Satellite Traffic Data API",
    description=(
        "Unified data layer for agentic decentralized satellite traffic negotiation. "
        "Aggregates TLE data, conjunction warnings, space weather, atmospheric density, "
        "and ground station contacts into a single satellite context payload."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(context.router, prefix="/v1")
app.include_router(orbital.router, prefix="/v1")
app.include_router(conjunctions.router, prefix="/v1")
app.include_router(space_weather.router, prefix="/v1")
app.include_router(ground_stations.router, prefix="/v1")


@app.get("/v1/health")
async def health():
    return {
        "status": "ok",
        "space_track_enabled": app.state.spacetrack is not None,
    }


@app.get("/v1/tools")
async def get_tool_definitions():
    """Returns OpenAI-compatible tool schemas for agent function calling."""
    from satellite_traffic_api.tools.definitions import SATELLITE_TOOLS
    return {"tools": SATELLITE_TOOLS}
