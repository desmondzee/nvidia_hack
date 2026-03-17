from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from satellite_traffic_api.config import settings
from satellite_traffic_api.cache.memory_backend import MemoryCacheBackend
from satellite_traffic_api.adapters.celestrak import CelesTrakAdapter
from satellite_traffic_api.adapters.spacetrack import SpaceTrackAdapter
from satellite_traffic_api.adapters.scenario_adapter import ScenarioAdapter, ScenarioState
from satellite_traffic_api.adapters.noaa_space_weather import NOAASpaceWeatherAdapter
from satellite_traffic_api.adapters.propagator import PropagatorAdapter
from satellite_traffic_api.adapters.nrlmsise import NRLMSISEAdapter
from satellite_traffic_api.adapters.ground_station import GroundStationAdapter
from satellite_traffic_api.aggregator.context_builder import SatelliteContextBuilder
from satellite_traffic_api.routers import context, orbital, conjunctions, space_weather, ground_stations, scenarios, negotiate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
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

    http_client = httpx.AsyncClient(
        headers={"User-Agent": "SatelliteTrafficAPI/1.0"},
        follow_redirects=True,
    )

    celestrak     = CelesTrakAdapter(settings, cache, http_client)
    noaa          = NOAASpaceWeatherAdapter(settings, cache, http_client)
    propagator    = PropagatorAdapter(settings, cache)
    nrlmsise      = NRLMSISEAdapter(settings, cache)
    ground_station = GroundStationAdapter(settings, cache)

    # Conjunction adapter: scenario mode takes priority over Space-Track
    scenario_id = os.environ.get("SCENARIO_MODE", "").strip()
    conjunction_adapter = None

    if scenario_id:
        conjunction_adapter = ScenarioAdapter(settings, cache, scenario_id)
        logger.info("SCENARIO MODE: using synthetic conjunctions from '%s'", scenario_id)
    elif settings.has_space_track:
        conjunction_adapter = SpaceTrackAdapter(settings, cache, http_client)
        logger.info("Space-Track adapter enabled for user: %s", settings.space_track_user)
    else:
        logger.warning(
            "No conjunction source configured — set SCENARIO_MODE=hero_collision "
            "or set SPACE_TRACK_USER + SPACE_TRACK_PASSWORD"
        )

    builder = SatelliteContextBuilder(
        celestrak=celestrak,
        spacetrack=conjunction_adapter,
        noaa=noaa,
        propagator=propagator,
        nrlmsise=nrlmsise,
        ground_station=ground_station,
    )

    app.state.cache              = cache
    app.state.celestrak          = celestrak
    app.state.spacetrack         = conjunction_adapter
    app.state.noaa               = noaa
    app.state.propagator         = propagator
    app.state.nrlmsise           = nrlmsise
    app.state.ground_station     = ground_station
    app.state.context_builder    = builder
    app.state.scenario_id        = scenario_id or None

    logger.info("Satellite Traffic API started")
    yield

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

app.include_router(context.router,        prefix="/v1")
app.include_router(scenarios.router,      prefix="/v1")
app.include_router(orbital.router,        prefix="/v1")
app.include_router(conjunctions.router,   prefix="/v1")
app.include_router(space_weather.router,  prefix="/v1")
app.include_router(ground_stations.router, prefix="/v1")
app.include_router(negotiate.router,      prefix="/v1")


@app.get("/v1/health")
async def health():
    return {
        "status": "ok",
        "scenario_mode": app.state.scenario_id,
        "space_track_enabled": (
            app.state.spacetrack is not None and app.state.scenario_id is None
        ),
    }


@app.post("/v1/demo/step/advance")
async def advance_demo_step():
    """Advance the demo to the next scenario step."""
    state = ScenarioState.get()
    new_step = state.advance()
    # Bust conjunction cache so new step is picked up immediately
    if app.state.scenario_id:
        await app.state.cache.delete(
            f"scenario:{app.state.scenario_id}:step:{new_step - 1}:{25544}"
        )
    return {"step": new_step}


@app.post("/v1/demo/step/reset")
async def reset_demo_step():
    """Reset demo back to step 1."""
    ScenarioState.get().reset()
    return {"step": 1}


@app.get("/v1/demo/step")
async def get_demo_step():
    """Get the current demo step."""
    return {"step": ScenarioState.get().current_step}


@app.get("/v1/tools")
async def get_tool_definitions():
    """Returns OpenAI-compatible tool schemas for agent function calling."""
    from satellite_traffic_api.tools.definitions import SATELLITE_TOOLS
    return {"tools": SATELLITE_TOOLS}
