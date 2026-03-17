# Synthetic Data Augmentation — Hero Collision Demo

## Overview

The demo uses a technique called **real-data augmentation**: live satellite telemetry from public APIs is fetched in real time, and a single synthetic field — the conjunction threat — is injected on top. The result is a `SatelliteContext` payload that is indistinguishable from production data except for the scripted collision scenario.

The synthetic data was generated once on the DGX Spark using Nemotron-Nano-30B, grounded by real orbital values fetched from the middleware at generation time. It is baked into `satellite_traffic_api/scenarios/hero_collision.json` and replayed deterministically during the demo.

---

## Why Augmentation, Not Full Simulation

A fully simulated scenario (fake TLEs, fake positions, fake everything) would not demonstrate the middleware working. The goal of the demo is to show that:

1. The middleware correctly aggregates live data from multiple sources
2. Agents can consume that data and make decisions
3. The system responds to a real threat escalation

Augmentation achieves this — the middleware does real work on every call, and only the conjunction field is scripted. The threat is plausible because it is geometrically consistent with where ISS actually is.

---

## What Needed to Be Augmented and Why

### What Could NOT Be Faked

The following fields must be live for the demo to be credible:

| Field | Why It Must Be Real |
|---|---|
| ISS position, velocity, altitude | Changes every second — a fake value would be obviously wrong to anyone tracking ISS |
| Orbital trajectory (24h) | Derived from the real TLE; must be consistent with current state |
| Space weather (Kp, solar wind) | Audience can verify against spaceweather.com in real time |
| Atmospheric density | Directly derived from real altitude + real Kp; consistency is checkable |
| Ground station passes | Computed from real geometry; pass times are publicly verifiable |

### What Was Augmented

**Conjunction events** — the predicted close approach between ISS and Starlink.

This is the only field replaced by synthetic data. The reasons:

1. **Real conjunctions are unpredictable** — a dramatic near-miss between ISS and a Starlink may or may not be happening on demo day. We cannot rely on one occurring.
2. **Real CDM data requires Space-Track credentials** — even with credentials, the data updates only 3× per day and may not show a compelling scenario.
3. **The conjunction field is self-contained** — it plugs into the `SatelliteContext` as a list of `ConjunctionEvent` objects with no dependencies on other live fields. Injecting it does not break any other part of the context.

---

## How the Synthetic Data Was Generated

### Step 1 — Pull Real Orbital Data from the Middleware

Before calling the LLM, the generation script fetches live data from the running satellite API:

```
GET /v1/satellites/25544/tle    → ISS orbital elements (inclination, eccentricity, etc.)
GET /v1/satellites/25544/state  → ISS actual position right now (altitude, lat, lon, speed)
GET /v1/satellites/44714/tle    → Starlink-1008 orbital elements
GET /v1/satellites/44714/state  → Starlink-1008 actual position
GET /v1/space-weather/current   → Current Kp index, atmospheric drag enhancement factor
```

At generation time, the values were:
- **ISS altitude**: 433.7 km
- **Starlink altitude**: 476.5 km
- **Space weather Kp**: 0.0 (quiet conditions)

### Step 2 — Build a Grounded Prompt

These real values were substituted into the LLM prompt as hard constraints:

```
REAL ORBITAL DATA (use these exact values as your baseline):

ISS (NORAD 25544):
  altitude_km:     433.69
  inclination_deg: 51.6338
  speed_km_s:      7.6498

STARLINK-1008 (NORAD 44714):
  altitude_km:     476.51
  inclination_deg: 53.1559
  speed_km_s:      7.6331
```

The prompt then asked for a 4-step escalation scenario with physics constraints:
- `relative_speed_km_s` must be identical across all steps (same orbital geometry — only tracking uncertainty narrows the miss distance)
- Miss distance vector components must satisfy `sqrt(r² + i² + c²) = miss_distance_km × 1000`
- Delta-v must be consistent with ISS thruster specs (~890N total, ~420,000 kg mass)

### Step 3 — Generate via Nemotron-Nano-30B on DGX Spark

The prompt was sent to the llama.cpp server running on the DGX Spark:

```
POST http://10.1.96.155:8080/v1/chat/completions
model: nemotron-nano-30b
temperature: 0.2
max_tokens: 8192
```

Nemotron is a reasoning model — it produces a chain of thought in `reasoning_content` before outputting the final answer in `content`. The low temperature (0.2) keeps the physics consistent rather than creative.

### Step 4 — Validate and Bake

The output was validated for physics consistency (miss distance vector components, speed consistency across steps) and written to:

```
satellite_traffic_api/scenarios/hero_collision.json
```

This file is committed to the repo and does not change at runtime. The generation only needs to happen once.

---

## The Generated Scenario

```json
{
  "step": 1, "risk_level": "NOMINAL",   "miss_distance_km": 35,   "tca_minutes": 95,
  "step": 2, "risk_level": "HIGH",      "miss_distance_km": 0.8,  "tca_minutes": 68,
  "step": 3, "risk_level": "CRITICAL",  "miss_distance_km": 0.15, "tca_minutes": 24,
  "step": 4, "risk_level": "NOMINAL",   "miss_distance_km": 18,   "tca_minutes": 0
}
```

**Maneuver**: ISS posigrade burn, 0.8 m/s delta-v, 380 seconds, raising altitude by 0.3 km, executed 22 minutes before TCA.

**Relative speed**: 7.65 km/s constant across all steps — consistent with the crossing geometry between ISS (51.6°) and Starlink (53.2°) inclination planes.

---

## How Augmentation Works at Runtime

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent API Call                            │
│         GET /v1/satellites/25544/context                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                 SatelliteContextBuilder                       │
│           asyncio.gather (all adapters concurrent)           │
└──┬──────────┬──────────┬──────────┬──────────┬──────────────┘
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
CelesTrak  ScenarioAdapter  NOAA   NRLMSISE  Skyfield
(LIVE TLE) (SYNTHETIC CDM) (LIVE)  (LIVE)    (LIVE)
```

The `ScenarioAdapter` implements the same `BaseAdapter` interface as the `SpaceTrackAdapter` it replaces. The context builder cannot tell the difference — it just calls `get_conjunctions(norad_id)` and gets back a list of `ConjunctionEvent` objects.

### Selection at Startup

```bash
SCENARIO_MODE=hero_collision uvicorn satellite_traffic_api.main:app --port 8001
```

When `SCENARIO_MODE` is set, `main.py` instantiates `ScenarioAdapter` instead of `SpaceTrackAdapter` as the conjunction source. All other adapters are identical to production.

### Step Control During Demo

The scenario step is held in a mutable singleton (`ScenarioState`). The demo operator advances it via:

```bash
POST /v1/demo/step/advance   # 1 → 2 → 3 → 4
POST /v1/demo/step/reset     # back to 1
GET  /v1/demo/step           # check current step
```

On every agent call to `/v1/satellites/25544/context`, the `ScenarioAdapter` reads the current step from `ScenarioState` and returns the matching conjunction data.

---

## Before and After the Middleware Layer

### Before the Middleware (Raw External Sources)

Without the middleware, an agent would need to:

| Task | Raw API Call | Complexity |
|---|---|---|
| Get orbital elements | `GET celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE` | Parse 3-line TLE format |
| Propagate position | Run SGP4 locally with sgp4 library | Orbital mechanics library required |
| Get conjunctions | Authenticate to space-track.org, POST login, then GET CDM query with date range | Session cookie auth, rate limits, CDM schema parsing |
| Get space weather | 4 separate NOAA SWPC endpoints: Kp, plasma, mag, alerts | Each returns different array-of-arrays format with header rows |
| Compute atmosphere | Run NRLMSISE-00 locally with F10.7 and Ap inputs | Requires local atmospheric model |
| Compute ground passes | Run skyfield with ground station coordinates | Requires orbital mechanics + ground station geometry |

Each source returns a different format. Some require authentication. None are aware of each other.

### What the Middleware Adds

The middleware normalizes, caches, and aggregates all of this into one call:

```python
ctx = httpx.get("http://localhost:8001/v1/satellites/25544/context").json()
```

The agent receives a single `SatelliteContext` object with ~350 scalar data points, already typed and validated, with a `collision_risk_level` field derived from all inputs and a `context_valid_until` timestamp telling it when to refresh.

### After the Middleware (What the Agent Sees)

```json
{
  "norad_cat_id": 25544,
  "object_name": "ISS (ZARYA)",
  "collision_risk_level": "CRITICAL",
  "recommended_action": "CRITICAL: Conjunction with STARLINK-1007 in 0.02 days at 0.150 km. Initiate collision avoidance maneuver planning immediately.",

  "current_state": {
    "altitude_km": 433.7,
    "latitude_deg": -40.5,
    "longitude_deg": -147.9,
    "speed_km_s": 7.65,
    "x_km": 5079.9, "y_km": -971.9, "z_km": -4421.9,
    "vx_km_s": 3.99, "vy_km_s": 5.60, "vz_km_s": 3.35
  },

  "conjunctions": [{
    "miss_distance_km": 0.15,
    "collision_probability": 0.0007,
    "tca": "2026-03-17T22:05:00Z",
    "secondary_object_name": "STARLINK-1007",
    "relative_speed_km_s": 7.65,
    "days_until_tca": 0.017
  }],

  "space_weather": {
    "current_kp": 0.0,
    "storm_level": "NONE",
    "atmospheric_drag_enhancement_factor": 1.0
  },

  "atmospheric_state": {
    "altitude_km": 433.7,
    "total_mass_density_kg_m3": 3.39e-12,
    "estimated_drag_acceleration_m_s2": 4.8e-7
  },

  "upcoming_ground_contacts": [
    {"ground_station_name": "Svalbard", "aos": "...", "los": "...", "max_elevation_deg": 23.4, "duration_seconds": 480}
  ],

  "orbit_next_24h": [ ...25 state vectors... ],
  "nearby_object_ids": [44714, 48274, ...],
  "context_valid_until": "2026-03-17T21:31:00Z"
}
```

The agent uses this to decide: is the threat real, do I have fuel to maneuver, is there a ground contact window before TCA to uplink the burn command, and what does the other agent want to do?

---

## Demo Flow

```
Step 1  NOMINAL   — agents running, real ISS context, no conjunction threat
        ↓  POST /v1/demo/step/advance
Step 2  HIGH      — synthetic 0.8km conjunction injected, agents alerted
        ↓  POST /v1/demo/step/advance
Step 3  CRITICAL  — synthetic 0.15km, P=7×10⁻⁴, agents negotiate maneuver
        ↓  POST /v1/demo/step/advance
Step 4  RESOLVED  — post-burn synthetic 18km miss distance, threat cleared
```

At every step, the agent is calling the same endpoint. The only thing changing is the conjunction field returned by `ScenarioAdapter`. ISS is at its real position, the atmosphere is real, the ground contacts are real. The collision is scripted — everything around it is live.
