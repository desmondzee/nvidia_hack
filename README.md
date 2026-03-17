# Satellite Traffic Data API

A unified data layer for agentic, decentralized satellite traffic negotiation. Each satellite agent calls a single endpoint to get a complete situational picture — orbital state, conjunction threats, space weather, atmospheric drag, and ground station contacts — without having to orchestrate multiple external APIs itself.

---

## What It Does

Each satellite in the system is operated by an autonomous agent. For those agents to make collision avoidance and traffic negotiation decisions, they need real-time context about:

- **Where they are** — current position, velocity, altitude
- **What's coming close** — predicted conjunctions with other satellites and debris
- **The environment** — space weather (solar storms increase atmospheric drag and degrade GPS)
- **Atmospheric drag** — density at the satellite's altitude affects orbital decay predictions
- **When they can talk to the ground** — upcoming contact windows for uplink/downlink

This service pulls data from multiple sources, normalizes it, caches it, and exposes it through a single clean API. Agents consume it via HTTP or via OpenAI-compatible tool call schemas.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Satellite Agent                      │
│   GET /v1/satellites/{norad_id}/context              │
└────────────────────────┬─────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────┐
│              SatelliteContextBuilder                  │
│  (aggregator — fans out to all adapters concurrently) │
└──┬──────────┬──────────┬──────────┬──────────┬───────┘
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
CelesTrak  SpaceTrack  NOAA SWPC  NRLMSISE  Skyfield
(TLE data) (CDM/conj.) (space wx) (atm. density) (ground passes)
```

All adapter calls are made concurrently with `asyncio.gather`. Results are cached (Redis or in-memory) so repeated agent polls within a decision loop are sub-millisecond.

---

## Data Sources

| Source | Data | Auth Required | Cache TTL |
|---|---|---|---|
| [CelesTrak](https://celestrak.org) | TLE orbital elements, active satellite catalog | None | 1 hour |
| [Space-Track.org](https://www.space-track.org) | Conjunction Data Messages (CDMs), close approach predictions | **Yes (free account)** | 30 min |
| [NOAA SWPC](https://services.swpc.noaa.gov) | Kp index, solar wind, geomagnetic storm level | None | 5 min |
| NRLMSISE-00 | Atmospheric density at satellite altitude | None (local computation) | 1 hour |
| SGP4 (local) | Orbital propagation — current position and 24h trajectory | None | 60 sec |
| Skyfield (local) | Ground station visibility pass calculation | None | 30 min |

---

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (package manager)
- A free [Space-Track.org](https://www.space-track.org/auth/createAccount) account for conjunction data

### Install

```bash
git clone <repo>
cd nvidia_hack

uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

uv pip install -e ".[dev]"
```

### Configure

```bash
cp .env.example .env
```

Open `.env` and fill in your Space-Track credentials:

```env
SPACE_TRACK_USER=your_email@example.com
SPACE_TRACK_PASSWORD=your_password
```

Everything else works out of the box. Conjunction data will be empty until credentials are set.

**Optional — Redis for shared cache across multiple API instances:**

```env
REDIS_URL=redis://localhost:6379/0
```

Without Redis, each process uses an in-memory cache. Fine for single-instance deployments.

### Run

```bash
uvicorn satellite_traffic_api.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`.

---

## API Endpoints

### Primary Agent Endpoint

```
GET /v1/satellites/{norad_id}/context
```

Returns a complete `SatelliteContext` — the full situational picture for one satellite. This is the single call an agent needs before any decision.

**Example** (ISS = NORAD 25544):
```bash
curl http://localhost:8000/v1/satellites/25544/context
```

**Response includes:**
- `current_state` — ECI position (km), velocity (km/s), lat/lon/altitude
- `orbit_next_24h` — hourly propagated positions for the next 24 hours
- `conjunctions` — all predicted close approaches, sorted by time of closest approach
- `high_risk_conjunctions` — filtered to miss distance < 1 km or collision probability > 1e-4
- `space_weather` — Kp index, storm level, solar wind, atmospheric drag enhancement factor
- `atmospheric_state` — NRLMSISE-00 density at satellite's current altitude
- `upcoming_ground_contacts` — AOS/LOS windows for configured ground stations
- `nearby_object_ids` — NORAD IDs of objects within 200 km
- `collision_risk_level` — `NOMINAL` | `ELEVATED` | `HIGH` | `CRITICAL`
- `recommended_action` — natural language summary (agents use this as a hint, not a directive)
- `context_valid_until` — when the agent should refresh (also in `X-Context-Expires` header)

---

### All Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/satellites/{norad_id}/context` | Full aggregated context (primary) |
| `GET` | `/v1/satellites/{norad_id}/tle` | Raw TLE orbital elements |
| `GET` | `/v1/satellites/{norad_id}/state` | Current propagated state vector |
| `GET` | `/v1/satellites/{norad_id}/conjunctions` | Conjunction events (needs Space-Track creds) |
| `GET` | `/v1/satellites/{norad_id}/ground-contacts` | Upcoming ground station passes |
| `GET` | `/v1/space-weather/current` | Space weather summary |
| `GET` | `/v1/tools` | OpenAI-compatible tool schemas for agents |
| `GET` | `/v1/health` | Service health + feature flags |

---

## Agent Integration

### HTTP

```python
import httpx

# Get full context for a satellite
ctx = httpx.get("http://localhost:8000/v1/satellites/25544/context").json()

print(ctx["collision_risk_level"])     # "NOMINAL"
print(ctx["recommended_action"])       # "NOMINAL. No action required."
print(ctx["current_state"]["altitude_km"])
```

### Function Calling (OpenAI / Anthropic / NVIDIA NIM)

Import the tool schemas directly — no HTTP server needed:

```python
from satellite_traffic_api.tools import SATELLITE_TOOLS

response = client.chat.completions.create(
    model="...",
    messages=[{"role": "user", "content": "Should satellite 25544 maneuver?"}],
    tools=SATELLITE_TOOLS,
)
```

Or fetch them from the running API:

```python
tools = httpx.get("http://localhost:8000/v1/tools").json()["tools"]
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `SPACE_TRACK_USER` | — | Space-Track.org email (required for conjunctions) |
| `SPACE_TRACK_PASSWORD` | — | Space-Track.org password |
| `REDIS_URL` | — | Redis connection string (optional) |
| `CACHE_TTL_TLE_SECONDS` | `3600` | TLE cache lifetime |
| `CACHE_TTL_CONJUNCTION_SECONDS` | `1800` | CDM cache lifetime |
| `CACHE_TTL_SPACE_WEATHER_SECONDS` | `300` | Space weather cache lifetime |
| `CONJUNCTION_LOOKAHEAD_DAYS` | `7` | How far ahead to query conjunctions |
| `NEARBY_RADIUS_KM` | `200` | Radius for nearby object detection |
| `GROUND_STATIONS` | 3 default stations | JSON list of ground station configs |

**Custom ground stations:**
```env
GROUND_STATIONS='[{"name":"Austin","lat":30.27,"lon":-97.74,"elevation_m":150,"min_elevation_deg":5}]'
```

---

## Project Structure

```
satellite_traffic_api/
├── main.py                     # FastAPI app + startup/shutdown
├── config.py                   # Settings (pydantic-settings, env vars)
├── models/
│   ├── orbital.py              # TLERecord, StateVector
│   ├── conjunction.py          # ConjunctionEvent
│   ├── space_weather.py        # SpaceWeatherSummary
│   ├── atmosphere.py           # AtmosphericState
│   ├── ground_station.py       # VisibilityWindow
│   └── context.py              # SatelliteContext (master payload)
├── adapters/
│   ├── base.py                 # Abstract BaseAdapter (cache-aside pattern)
│   ├── celestrak.py            # TLE data
│   ├── spacetrack.py           # Conjunction data (auth required)
│   ├── noaa_space_weather.py   # Kp, solar wind
│   ├── nrlmsise.py             # Atmospheric density (local)
│   ├── propagator.py           # SGP4 orbit propagation (local)
│   └── ground_station.py       # Visibility passes via skyfield (local)
├── cache/
│   ├── backend.py              # Abstract CacheBackend
│   ├── memory_backend.py       # In-process TTL dict
│   └── redis_backend.py        # Redis (optional)
├── aggregator/
│   └── context_builder.py      # Orchestrates all adapters → SatelliteContext
├── routers/                    # FastAPI route handlers
└── tools/
    └── definitions.py          # OpenAI-compatible tool schemas
```

---

## Adding a New Data Source

1. Create `satellite_traffic_api/adapters/my_source.py` implementing `BaseAdapter`
2. Add a Pydantic model to `satellite_traffic_api/models/`
3. Register the adapter in `main.py` and wire it into `SatelliteContextBuilder`
4. Add the field to `SatelliteContext` or use the `extensions` dict for a non-breaking addition

---

## Notes

- **NORAD IDs** are the standard identifier. Look them up at [celestrak.org/satcat](https://celestrak.org/satcat) or [n2yo.com](https://www.n2yo.com).
- `collision_risk_level` and `recommended_action` are derived heuristics — agents should apply their own reasoning on top of the raw data.
- Space-Track CDM data is updated ~3× per day by the 18th Space Control Squadron. The 30-minute cache TTL is intentionally conservative.
- The NRLMSISE-00 atmospheric model runs locally and uses current space weather (F10.7, Ap) from NOAA to account for solar activity effects on drag.
