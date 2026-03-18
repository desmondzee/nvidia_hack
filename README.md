# Sentinel — Decentralized Agentic Space Traffic Negotiation

## The Crisis: Orbital Congestion is a Climate Emergency

With over 14,000 active satellites and 40,000+ tracked pieces of debris in Low Earth Orbit (LEO), we are accelerating toward **Kessler Syndrome**—a runaway chain reaction of collisions. But this isn't just an operational hazard; it is an active, escalating environmental crisis.

- **Stratospheric Metal Pollution:** When satellites and debris burn up upon reentry, they deposit aluminum oxide and spacecraft alloys directly into the stratosphere. These metallic aerosols are already altering polar vortex dynamics, warming the mesosphere, and catalyzing ozone depletion.
- **The Carbon Multiplier of Collisions:** A single rocket launch produces upwards of 425 metric tonnes of CO₂-equivalent. A debris cascade that destroys hundreds of satellites would mandate hundreds of replacement launches, generating hundreds of thousands of tonnes of avoidable emissions.
- **Propellant Waste:** Current human-in-the-loop avoidance maneuvers are uncoordinated, causing operators to burn finite propellant unnecessarily on false alarms. This shortens satellite lifespans and forces premature replacement launches.

The current Space Traffic Management system—which relies on centralized ground control and takes hours to days to negotiate a single maneuver—**cannot scale** to prevent this ecological disaster.

---

## The Solution: Decentralized Agentic Negotiation

We propose a paradigm shift: each satellite is represented by an **autonomous AI agent** that continuously monitors risk and negotiates avoidance maneuvers directly with peer satellites in **seconds**.

Our system operates across three autonomous layers:

1. **Unified Data Layer:** Aggregates real-time TLEs, Conjunction Data Messages (CDMs), and NOAA space weather into a single, actionable context payload.
2. **Agentic Negotiation (LangGraph):** When collision risk is critical, the agent initiates a bilateral negotiation protocol. It proposes a concrete, fuel-efficient maneuver, evaluates counter-proposals, and commits to a mathematically sound delta-V burn in seconds.
3. **Memory & Learning (RAG):** Using NVIDIA NIM embeddings and a Milvus vector database, agents recall past negotiations across the fleet to continuously optimize fuel efficiency and maneuver success rates.

---

## Powered Locally by NVIDIA

To execute life-or-death maneuvers, we must sever our reliance on high-latency cloud servers.

- **Edge Sovereignty via DGX Spark:** The entire system runs locally on the NVIDIA DGX Spark. Its 128GB of unified memory allows us to run complex, multi-agent reasoning at the edge with zero network latency.
- **Auditable Reasoning with Nemotron-Nano-30B:** The LLM does not just output text; it produces typed Pydantic objects. The model generates an explicit `reasoning_content` chain-of-thought, providing operators and regulators with a transparent, inspectable audit trail for every thruster burn.

---

## Open Source by Necessity

Space safety is a global commons problem. Satellite traffic negotiation requires bilateral agreement between competing operators. By open-sourcing the agent-to-agent protocol and the inference stack, we provide an auditable, transparent safety layer that prevents vendor lock-in, ensures regulatory compliance, and democratizes orbital safety.

**The cost of inaction is an orbital debris cascade that poisons our stratosphere and shuts down the space economy. The solution is running locally on a DGX Spark today.**

---

## Data & Library Dependencies

| Category | Provider / Library | Notes |
|----------|--------------------|-------|
| **Open Source Data (free, no auth)** | CelesTrak | Live TLE orbital elements for all tracked objects |
| | NOAA SWPC | Real-time space weather (Kp index, F10.7 solar flux, Ap geomagnetic index) |
| **Open Source Libraries (local)** | SGP4 (`sgp4`) | Standard orbital propagation algorithm |
| | NRLMSISE-00 (`nrlmsise00`) | Atmospheric density model from the Naval Research Laboratory |
| | Skyfield | Ground station visibility pass computation |
| | NumPy / SciPy | Vector math and orbital geometry |
| | XGBoost | Collision risk classification |
| **Proprietary / Credentialed (optional)** | Space-Track.org | Conjunction data messages; requires free account registration with the U.S. Space Force |

---

# System Workflow — Satellite Collision Avoidance Pipeline

End-to-end walkthrough of every step, from raw orbital data through LLM-driven negotiation to a maneuver decision.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        satellite_traffic_api  (:8000)                    │
│                                                                           │
│  CelesTrak ──► TLE / Catalog                                             │
│  SpaceTrack ──► CDMs (conjunctions)        ┌─────────────────────────┐  │
│  ScenarioAdapter ──► synthetic CDMs   ───► │  SatelliteContextBuilder │  │
│  NOAA SWPC ──► space weather               │  + CollisionClassifier   │  │
│  NRLMSISE-00 ──► atmospheric density       │  (XGBoost + rules)       │  │
│  Skyfield ──► ground station passes        └──────────┬──────────────┘  │
│                                                        │ SatelliteContext│
│                                            ┌───────────▼──────────────┐  │
│                                            │   negotiate.py router    │  │
│                                            │ POST /v1/satellites/     │  │
│                                            │       {id}/negotiate     │  │
│                                            └───────────┬──────────────┘  │
│                                                        │ EnrichedCollision│
│                                                        │ Alert (JSON)     │
└────────────────────────────────────────────────────────┼─────────────────┘
                                                         │ POST /negotiate
┌────────────────────────────────────────────────────────▼─────────────────┐
│                        sentinel_agent  (:8001)                            │
│                                                                           │
│  negotiate_api.py ──► EnrichedCollisionAlert → CollisionAlert             │
│                                                                           │
│  runner.py ──► LangGraph initiator graph  ──► LLM (NVIDIA/Google/Ollama) │
│               LangGraph responder graph  ◄──►                            │
│               InMemoryChannel (message passing)                          │
│                                                                           │
│  Returns: ManeuverDecision                                                │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1 — Startup (`satellite_traffic_api`)

**File:** [satellite_traffic_api/main.py](satellite_traffic_api/main.py)

When the server starts, `lifespan()` initialises every adapter and stores them in `app.state`:

| Component | Class | Role |
|---|---|---|
| `cache` | `MemoryCacheBackend` (or `RedisCacheBackend`) | Caches all external API responses with per-source TTLs |
| `celestrak` | `CelesTrakAdapter` | Fetches TLE data from `celestrak.org` |
| `spacetrack` / `scenario` | `SpaceTrackAdapter` or `ScenarioAdapter` | Fetches or generates conjunction (CDM) data |
| `noaa` | `NOAASpaceWeatherAdapter` | Fetches Kp, F10.7, solar wind from NOAA SWPC |
| `propagator` | `PropagatorAdapter` | SGP4 orbital propagation |
| `nrlmsise` | `NRLMSISEAdapter` | NRLMSISE-00 atmospheric density model |
| `ground_station` | `GroundStationAdapter` | Skyfield-based ground pass visibility |
| `context_builder` | `SatelliteContextBuilder` | Aggregates all of the above into one payload |

**Conjunction source selection:**

```
if SCENARIO_MODE env var is set:
    use ScenarioAdapter (reads hero_collision.json)
elif SPACE_TRACK_USER + SPACE_TRACK_PASSWORD are set:
    use SpaceTrackAdapter (real CDMs from space-track.org)
else:
    no conjunction source — risk will always be NOMINAL
```

**XGBoost classifier** is also trained at this point (module import of `context_builder.py` triggers `_classifier = CollisionClassifier()` which trains on 400 synthetic samples).

---

## Part 2 — Demo Scenario Data (`ScenarioAdapter`)

**File:** [satellite_traffic_api/adapters/scenario_adapter.py](satellite_traffic_api/adapters/scenario_adapter.py)

`hero_collision.json` encodes a 4-step collision escalation between **ISS (NORAD 25544)** and **Starlink-1007 (NORAD 44713)**. The scenario was generated once by Nemotron-Nano-30B on a DGX Spark using real orbital data fetched at generation time as constraints.

| Step | Risk | Miss Distance | Pc | TCA Minutes Away | Meaning |
|---|---|---|---|---|---|
| 1 | NOMINAL | 35.0 km | — | 95 | No threat, monitoring only |
| 2 | HIGH | 0.8 km | 5 × 10⁻⁵ | 68 | Conjunction detected, alert raised |
| 3 | CRITICAL | 0.15 km | 7 × 10⁻⁴ | 24 | Emergency — maneuver required |
| 4 | NOMINAL | 18.0 km | — | 0 | Post-burn, threat cleared |

**At runtime**, `ScenarioAdapter.get_conjunctions(norad_id)` reads `ScenarioState.current_step` and returns the matching `ConjunctionEvent`. Steps 1 and 4 return an empty list (no conjunction).

**Demo step control:**
```
POST /v1/demo/step/advance   → step 1 → 2 → 3 → 4
POST /v1/demo/step/reset     → back to 1
GET  /v1/demo/step           → current step
```

---

## Part 3 — Building Satellite Context (`SatelliteContextBuilder`)

**File:** [satellite_traffic_api/aggregator/context_builder.py](satellite_traffic_api/aggregator/context_builder.py)

Triggered by any call that needs satellite context (e.g., `POST /v1/satellites/25544/negotiate`).

### Step 3.1 — Fetch TLE
```
CelesTrakAdapter.get_tle(norad_id)
  → GET celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE
  → Parse 3-line TLE → TLERecord (inclination, eccentricity, RAAN, etc.)
  → Cache key: celestrak:tle:norad:25544   TTL: 3600s
```

### Step 3.2 — Concurrent Fan-Out
Five sources are fetched simultaneously via `asyncio.gather`:

| Source | Data | Cache TTL |
|---|---|---|
| `PropagatorAdapter.get_state(tle)` | Current ECI position/velocity, lat/lon/alt, speed | 60s |
| `NOAASpaceWeatherAdapter.get_current()` | Kp index, F10.7, Ap, storm level, drag enhancement factor | 300s |
| `ScenarioAdapter.get_conjunctions(norad_id)` | List of `ConjunctionEvent` objects for current step | 10s |
| `GroundStationAdapter.get_contacts(tle)` | Next ground station passes (AOS, LOS, max elevation) | 1800s |
| *(atmospheric wait for step below)* | | |

### Step 3.3 — Atmospheric Density
```
NRLMSISEAdapter.get_atmospheric_state(altitude_km, lat, lon, datetime, f107, ap)
  → Run NRLMSISE-00 atmospheric model locally
  → Returns total_mass_density_kg_m3, estimated_drag_acceleration_m_s2
  → Cache key: nrlmsise:{alt}:{lat}:{lon}   TTL: 3600s
```

### Step 3.4 — Trajectory + Nearby Objects
```
PropagatorAdapter.get_trajectory(tle, hours=24)
  → SGP4 propagation at hourly intervals × 25 points
  → Returns list[StateVector]

CelesTrakAdapter.get_active_catalog()
  → GET celestrak.org/NORAD/elements/?GROUP=active&FORMAT=TLE
  → ~8,000 active satellites
  → Cache key: celestrak:tle:group:active   TTL: 3600s

PropagatorAdapter.get_nearby(tle, active_catalog, radius_km=200)
  → Propagate each catalog object to now, compute 3D distance
  → Return objects within 200 km
```

### Step 3.5 — Risk Classification

**Rule-based (hard thresholds):**
```python
for c in conjunctions:
    if c.miss_distance_km < 0.2 or Pc > 1e-3:   → CRITICAL
    if c.miss_distance_km < 1.0 or Pc > 1e-4:   → HIGH
    if c.miss_distance_km < 5.0 or Kp >= 7:     → ELEVATED
    else:                                         → NOMINAL
```

**XGBoost ML classifier** (runs in parallel):

8 features extracted per conjunction:

| # | Feature | Source | Notes |
|---|---|---|---|
| 0 | `miss_distance_km` | ConjunctionEvent | Log-scale in training |
| 1 | `collision_probability` | ConjunctionEvent | 0.0 when absent |
| 2 | `has_collision_probability` | derived | 0/1 flag |
| 3 | `relative_speed_km_s` | ConjunctionEvent | Default 7.5 if null |
| 4 | `days_until_tca` | ConjunctionEvent | Urgency signal |
| 5 | `object_type_encoded` | ConjunctionEvent | PAYLOAD=0, UNKNOWN=1, ROCKET_BODY=2, DEBRIS=3 |
| 6 | `current_kp` | SpaceWeatherSummary | Geomagnetic storm uncertainty |
| 7 | `atmospheric_drag_enhancement_factor` | SpaceWeatherSummary | TCA prediction degradation |

Feature interactions captured (bumped during training, not available to rules):
- **Speed + proximity**: speed > 10 km/s AND miss < 2 km → +1 risk level
- **Imminence**: days_until_tca < 1.0 AND miss < 5 km → +1 risk level
- **Debris proximity**: DEBRIS type AND miss < 3 km → +1 risk level

**Final risk** = `max(rule_risk, ml_risk)` — rules are always the safety floor.

### Step 3.6 — Assemble SatelliteContext

Output model `SatelliteContext` contains:
- `norad_cat_id`, `object_name`, `fetched_at`, `context_valid_until`
- `tle` (TLERecord)
- `current_state` (StateVector: ECI x/y/z, vx/vy/vz, lat/lon/alt, speed)
- `orbit_next_24h` (25 hourly StateVectors)
- `conjunctions` (all ConjunctionEvent objects for this step)
- `high_risk_conjunctions` (filtered: miss < 1 km or Pc > 1e-4)
- `space_weather` (SpaceWeatherSummary)
- `atmospheric_state` (AtmosphericState)
- `upcoming_ground_contacts` (list of VisibilityWindow)
- `nearby_object_ids` / `nearby_object_names`
- `collision_risk_level` (NOMINAL / ELEVATED / HIGH / CRITICAL)
- `recommended_action` (human-readable string)
- `data_freshness` (per-source ISO timestamps)

---

## Part 4 — Collision Detection & Alert Building (`negotiate.py`)

**File:** [satellite_traffic_api/routers/negotiate.py](satellite_traffic_api/routers/negotiate.py)

Triggered by `POST /v1/satellites/{norad_id}/negotiate` or by `POST /v1/demo/run`.

### Step 4.1 — Risk Gate
```
if collision_risk_level < HIGH:
    return {"status": "no_action", "risk_level": ...}
```
Steps 1 and 4 of the demo scenario exit here.

### Step 4.2 — Select Worst Conjunction
Filters conjunctions where miss < 1 km or Pc > 1e-4, then sorts by (miss_distance_km, tca). Falls back to closest miss if none qualify.

### Step 4.3 — Propagate Both Objects to TCA (SGP4)
```
our_state_at_tca  = propagator.propagate_to_time(our_tle, worst.tca)
threat_tle        = celestrak.get_tle(worst.secondary_norad_id)
threat_state_at_tca = propagator.propagate_to_time(threat_tle, worst.tca)
```
If the threat TLE is unavailable, position is estimated from geometry (miss distance on radial axis) and relative velocity is approximated from the CDM's `relative_speed_km_s`.

### Step 4.4 — Assemble `EnrichedCollisionAlert`

This is the bridge schema — everything the negotiation LLM needs in a single payload.

| Section | Fields |
|---|---|
| **Identity** | `alert_id` (ECA-{event_id}-{uuid}), `generated_at`, `cdm_source` |
| **Core conjunction** | `time_of_closest_approach`, `time_to_tca_seconds`, `miss_distance_m`, `probability_of_collision`, `relative_velocity_km_s` |
| **Space objects at TCA** | `our_object` and `threat_object` — each with `object_id`, `object_name`, `object_type`, `position_km` (ECI), `velocity_km_s` (ECI) |
| **Threat level** | `threat_level`: "low" / "medium" / "high" / "critical" |
| **Risk detail** | `rule_based_risk`, `ml_risk`, `final_risk`, `recommended_action` |
| **Space weather** | `kp_index`, `kp_24h_max`, `storm_level`, `solar_flux_f10_7`, `f107_81day_avg`, `ap_daily`, `atmospheric_drag_enhancement_factor`, `active_alerts` |
| **Atmospheric** | `atmospheric_density_kg_m3`, `atmospheric_drag_acceleration_m_s2` |
| **Multi-threat** | `total_active_conjunctions`, `other_high_risk_conjunctions[]` |
| **Ground contact** | `minutes_to_next_ground_contact`, `next_ground_station_name` |
| **Provenance** | `data_freshness` (per-source), `raw_conjunction_data` (full CDM dump) |

### Step 4.5 — POST to sentinel_agent
```
POST http://localhost:8001/negotiate
Content-Type: application/json
Body: EnrichedCollisionAlert (JSON)
Timeout: 120s
```
If sentinel_agent is unreachable, returns `status="alert_only"` with the full alert but no negotiation result (graceful degradation).

---

## Part 5 — Negotiation Ingest (`sentinel_agent`)

**File:** [sentinel_agent/src/negotiate_api.py](sentinel_agent/src/negotiate_api.py)

### Step 5.1 — Schema Conversion
```
EnrichedCollisionAlert.to_collision_alert()
  → CollisionAlert(
      alert_id, time_of_closest_approach,
      our_object=SpaceObject(position=Vector3, velocity=Vector3, ...),
      threat_object=SpaceObject(...),
      miss_distance_m, probability_of_collision,
      threat_level=ThreatLevel(self.threat_level),
      relative_velocity=Vector3(...),
      time_to_tca_seconds,
      weather_parameters,
      raw_cdm_data,
    )
```

`EnrichedCollisionAlert` (600+ fields, full environment) → `CollisionAlert` (minimal physics model for LLM).

### Step 5.2 — Run Simulation
```
run_simulation_from_alert(alert, llm_provider="nvidia")
```
Returns `(ManeuverDecision | None, result_dict)`.

---

## Part 6 — LLM Negotiation (`runner.py` + `negotiation_agent.py`)

**Files:** [sentinel_agent/src/simulation/runner.py](sentinel_agent/src/simulation/runner.py), [sentinel_agent/src/agents/negotiation_agent.py](sentinel_agent/src/agents/negotiation_agent.py)

### Setup

```python
sat_a = alert.our_object.object_id        # ISS — the initiator
sat_b = alert.threat_object.object_id     # Starlink-1007 — the responder

# Mirror: flip our/threat perspective so responder sees itself as "our_object"
alert_b = _mirror_alert(alert)

# Two in-memory async message queues
channel_a_to_b = InMemoryChannel()   # initiator → responder
channel_b_to_a = InMemoryChannel()   # responder → initiator

initiator_graph = build_initiator_graph(llm, max_rounds=3)
responder_graph = build_responder_graph(llm, max_rounds=3)
```

Both graphs run **concurrently** via `asyncio.gather`.

### LangGraph — Initiator Graph

**State:** `InitiatorState`

```
collision_alert, our_satellite_id, peer_satellite_id, session_id
current_round (1–3), max_rounds (3)
messages_log (append-only)
outbound_proposal, inbound_response
peer_accepted (bool | None)
final_decision (ManeuverDecision | None)
analysis_notes, sharing_strategy
```

**Nodes and what each LLM call does:**

```
START
  ↓
analyze_collision
  LLM prompt: "Assess severity. Who should maneuver? What data is safe to share?"
  Output: severity_assessment, who_should_maneuver, sharing_strategy, proposal_type
  ↓
generate_proposal
  LLM prompt: "Generate delta-v vector, burn time, duration, expected new miss distance."
  (Round > 1: "Consider peer's counter-proposal, find a compromise.")
  Output: shared_data, proposal_type, proposed_maneuver, reasoning
  → sends NegotiationMessage (PROPOSAL phase) to channel_a_to_b
  ↓
await_response
  → blocks on channel_b_to_a.receive_message(timeout=120s)
  → receives NegotiationMessage (RESPONSE phase) from responder
  ↓
evaluate_response
  (only called if peer_accepted == False)
  LLM prompt: "Evaluate peer's counter-proposal. Accept it, or prepare another round?"
  Output: accept (bool), reasoning, counter_maneuver
  ↓
  ┌──────────────────────────────────────────┐
  │ _should_continue_or_decide():            │
  │   peer_accepted == True   → make_decision │
  │   round >= max_rounds     → make_decision │
  │   otherwise               → increment_round → generate_proposal (loop) │
  └──────────────────────────────────────────┘
  ↓
make_decision
  LLM prompt: "Based on full negotiation history, produce final maneuver.
               If no agreement: choose safest unilateral maneuver. Safety first."
  Output: agreed (bool), our_maneuver, peer_maneuver, summary
  → builds ManeuverDecision
  ↓
END
```

### LangGraph — Responder Graph

**State:** `ResponderState`

```
collision_alert, our_satellite_id, peer_satellite_id
session_id, current_round, max_rounds
inbound_proposal (NegotiationMessage)
evaluation_result (EvaluationOutput | None)
outbound_response (NegotiationMessage | None)
messages_log
```

**Nodes:**

```
START
  ↓
receive_proposal   (pass-through node — proposal already in state)
  ↓
evaluate_proposal
  LLM prompt: "Assess peer's proposal. Does it adequately resolve the risk?
               Is fuel cost distribution fair? Accept or counter-propose?"
  Output: accept (bool), reasoning, counter_maneuver (required if rejecting)
  ↓
generate_response
  Builds NegotiationMessage (RESPONSE phase) with accepted=True/False
  → sends to channel_b_to_a
  ↓
END
```

**Responder loop** (in runner.py): called once per round, blocking on channel:
```python
for round in range(1, max_rounds + 1):
    proposal = await channel_a_to_b.receive_message(timeout=120s)
    result = await responder_graph.ainvoke(state_with_proposal)
    if result["outbound_response"].accepted:
        break   # stop early — agreement reached
```

### Round-by-Round Flow

**Round 1:**
1. Initiator analyzes collision → generates maneuver proposal → sends to channel
2. Responder receives → evaluates → responds (accept/reject + optional counter)
3. Initiator receives response

**Round 2** (if rejected):
4. Initiator generates counter-proposal incorporating responder's feedback
5. Responder evaluates new proposal → responds

**Round 3** (if still rejected):
6. Final negotiation attempt
7. If still no agreement → initiator produces safest unilateral maneuver

**All LLM calls use `llm.with_structured_output(Schema)` — temperature 0.2.**

### NegotiationMessage Contents

```
message_id, session_id, round_number (1–3)
phase: PROPOSAL | RESPONSE
sender_satellite_id, receiver_satellite_id
timestamp

collision_data: SharedCollisionData
  → alert_id, tca, miss_distance_m, probability_of_collision,
     threat_level, our_object_id, our_planned_position, relative_velocity_magnitude

proposal_type: MANEUVER_REQUEST | MANEUVER_OFFER | SHARED_MANEUVER
proposed_maneuver: ProposedManeuver
  → delta_v: Vector3 (m/s, RTN frame)
  → burn_start_time: datetime
  → burn_duration_seconds: float
  → expected_miss_distance_after_m: float
  → fuel_cost_estimate: float | None

reasoning: str    (LLM chain-of-thought justification)
accepted: bool | None   (set in RESPONSE phase)
counter_proposal: ProposedManeuver | None   (set if rejecting)
```

---

## Part 7 — Response Chain Back to Caller

```
ManeuverDecision {
    session_id, alert_id
    our_satellite_id, peer_satellite_id
    agreed: bool
    our_maneuver: ProposedManeuver | None   (what ISS will do)
    peer_maneuver: ProposedManeuver | None  (what Starlink-1007 agreed to do)
    negotiation_summary: str
    rounds_taken: int (1–3)
    decided_at: datetime
}
```

This is returned by sentinel_agent → satellite_traffic_api `negotiate.py` router → caller.

---

## Part 8 — Demo Run (`POST /v1/demo/run`)

**File:** [satellite_traffic_api/main.py](satellite_traffic_api/main.py) (line ~151)

Single endpoint that orchestrates the complete 4-step scenario:

```
POST /v1/demo/run
  │
  ├── ScenarioState.reset()  →  step = 1
  │
  ├── Step 1: run_negotiate_pipeline(25544)
  │     ScenarioAdapter returns [] (no conjunction at step 1)
  │     SatelliteContext.collision_risk_level = NOMINAL
  │     → {"status": "no_action", "risk_level": "NOMINAL"}
  │
  ├── ScenarioState.advance()  →  step = 2
  ├── cache.delete("scenario:hero_collision:step:1:25544")
  │
  ├── Step 2: run_negotiate_pipeline(25544)
  │     ScenarioAdapter returns ConjunctionEvent(miss=0.8km, Pc=5e-5, days=0.047)
  │     rule_risk = HIGH, ml_risk = HIGH  →  final = HIGH
  │     Propagate ISS + Starlink to TCA
  │     Build EnrichedCollisionAlert
  │     POST to sentinel_agent /negotiate
  │     LLM runs 1–3 round negotiation
  │     → {"status": "triggered", "risk_level": "HIGH", "alert": {...}, "negotiation_result": {...}}
  │
  ├── ScenarioState.advance()  →  step = 3
  ├── cache.delete("scenario:hero_collision:step:2:25544")
  │
  ├── Step 3: run_negotiate_pipeline(25544)
  │     ScenarioAdapter returns ConjunctionEvent(miss=0.15km, Pc=7e-4, days=0.017)
  │     rule_risk = CRITICAL, ml_risk = CRITICAL  →  final = CRITICAL
  │     Propagate both objects to TCA (24 minutes away)
  │     Build EnrichedCollisionAlert  (miss_distance_m = 150)
  │     POST to sentinel_agent /negotiate
  │     LLM negotiation — likely agrees on ISS posigrade burn ≈ 0.8 m/s
  │     → {"status": "triggered", "risk_level": "CRITICAL", "alert": {...}, "negotiation_result": {...}}
  │
  ├── ScenarioState.advance()  →  step = 4
  ├── cache.delete("scenario:hero_collision:step:3:25544")
  │
  └── Step 4: run_negotiate_pipeline(25544)
        ScenarioAdapter returns [] (post-burn, miss=18km, NOMINAL)
        SatelliteContext.collision_risk_level = NOMINAL
        → {"status": "no_action", "risk_level": "NOMINAL"}

Returns:
{
  "scenario": "hero_collision",
  "steps": [
    {"step": 1, "status": "no_action",  "risk_level": "NOMINAL"},
    {"step": 2, "status": "triggered",  "risk_level": "HIGH",     "alert": {...}, "negotiation_result": {...}},
    {"step": 3, "status": "triggered",  "risk_level": "CRITICAL", "alert": {...}, "negotiation_result": {...}},
    {"step": 4, "status": "no_action",  "risk_level": "NOMINAL"}
  ]
}
```

---

## LLM Providers

**File:** [sentinel_agent/src/agents/llm.py](sentinel_agent/src/agents/llm.py)

| Provider | Model | Env Var | Notes |
|---|---|---|---|
| `nvidia` (default) | `nvidia/llama-3.3-nemotron-super-49b-v1` | `NVIDIA_API_KEY` | NVIDIA NIM cloud; same family as Nemotron-Nano-30B used for data generation |
| `google` | `gemini-3-flash-preview` | `GOOGLE_API_KEY` | Google cloud API |
| `ollama` | configurable (`OLLAMA_MODEL`, default `llama3.2`) | `OLLAMA_BASE_URL` | Local inference; auto-falls back to Google if unavailable |

Set via env var: `SENTINEL_LLM_PROVIDER=nvidia|google|ollama`

All providers use `temperature=0.2` for deterministic physics reasoning.

---

## Cache TTLs

| Source | TTL | Reason |
|---|---|---|
| TLE (single satellite) | 3600s | TLEs update once or twice daily |
| TLE (active catalog) | 3600s | Same |
| Conjunctions / CDMs | 1800s | Space-Track updates 3× per day |
| Scenario conjunctions | 10s | Short so step advances are detected quickly |
| Space weather | 300s | Kp updates every 3 minutes |
| Propagation | 60s | Position changes significantly each minute |
| Ground contacts | 1800s | Pass windows don't change frequently |
| Atmospheric density | 3600s | Changes slowly unless Kp spikes |

---

## Running End-to-End

```bash
# 1. Install dependencies (Python 3.12)
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd sentinel_agent && ../.venv/bin/pip install -e ".[dev]" && cd ..

# 2. Configure credentials
echo "NVIDIA_API_KEY=nvapi-..." > .env
echo "SENTINEL_LLM_PROVIDER=nvidia" >> sentinel_agent/.env

# 3. Start satellite_traffic_api (scenario mode)
SCENARIO_MODE=hero_collision .venv/bin/uvicorn satellite_traffic_api.main:app --port 8000

# 4. Start sentinel_agent
cd sentinel_agent
../.venv/bin/uvicorn src.negotiate_api:app --port 8001

# 5. Run full pipeline
curl -X POST http://localhost:8000/v1/demo/run | python3 -m json.tool

# 6. Or trigger a specific step manually
curl -X POST http://localhost:8000/v1/demo/step/advance   # advance to step 2
curl -X POST http://localhost:8000/v1/satellites/25544/negotiate
```
