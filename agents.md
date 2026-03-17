# SENTINEL — Technical Architecture: Agents, Collision Detection & Orbit Visualization

This document explains the full technical pipeline for how SENTINEL detects satellite collisions, draws orbit paths, and orchestrates AI agents across two codebases:
- **nvidia_hack**: Next.js frontend for real-time visualization
- **honeycomb.ai**: Advanced mission planning backend with physics-based orbital mechanics and AI agent orchestration

---

## 1. TLE Data Fetching & Processing

### Step 1 — TLE Acquisition (`src/app/api/tle/route.ts`)

The app fetches live Two-Line Element (TLE) data from the **SatNOGS public API**:

```
GET https://db.satnogs.org/api/tle/?format=json&ordering=-updated&limit=500
```

- **Cache duration**: 1 hour (3600s)
- **Timeout**: 8 seconds
- **Fallback**: Hardcoded TLE set for 43 satellites (Starlink, NOAA, ISS, GOES, Sentinel) using 2026 epoch, triggered if the API is unreachable

**SatNOGS response format:**
```typescript
interface SatNOGSEntry {
  tle0: string;  // "0 SATELLITE NAME"
  tle1: string;  // TLE line 1, starts with "1 "
  tle2: string;  // TLE line 2, starts with "2 "
}
```

The route filters valid pairs (both lines at least 69 chars), strips the "0 " name prefix, and returns everything as a single newline-separated TLE string.

### Step 2 — TLE Parsing (`src/lib/tle.ts`)

`parseTLEText(text: string): SatelliteData[]` iterates the text in groups of 3 lines:

```typescript
// Validation: must start with "1 " and "2 ", min 69 chars each
const noradId = tle1.substring(2, 7).trim();  // NORAD ID from positions 2–7

interface SatelliteData {
  id: string;    // NORAD ID (e.g., "25544")
  name: string;  // e.g., "ISS (ZARYA)"
  tle1: string;
  tle2: string;
  position?: Vec3;
  lat?: number;
  lon?: number;
  alt?: number;
}
```

### Step 3 — State Population (`src/stores/satelliteStore.ts`)

The parsed array is stored in a **Zustand** store:

```typescript
interface SatelliteState {
  satellites: SatelliteData[];
  selectedSatellite: SatelliteData | null;
  isPlaying: boolean;
  playbackSpeed: number;    // 1, 10, 60, 300, 1000 ×
  currentTime: Date;        // Simulation epoch
  viewMode: "global" | "collision";
}
```

Default playback speed is **60×** (1 simulated minute per real second), starting at today's midnight UTC.

---

## 2. Orbit Path Drawing & Real-Time Visualization

### Step 4 — Cesium.js Loading (`src/lib/cesium.ts`)

CesiumJS v1.122 is loaded from CDN via a single lazy promise to prevent double-loads:

```typescript
export async function loadCesium(): Promise<void> {
  // 1. Inject CSS stylesheet into DOM
  // 2. Load Cesium.js script
  // 3. Set Ion access token
  // 4. Resolve when window.Cesium is available
}
```

### Step 5 — Globe Initialization (`src/components/GlobeViewer.tsx`)

The Cesium viewer is created with a minimal UI (no timeline, no geocoder) and configured with:

- **Imagery**: NASA GIBS Blue Marble tiles (`gibs.earthdata.nasa.gov/wmts/...`)
- **Lighting**: Day/night simulation with `globe.enableLighting = true`
- **Background**: Deep space black (`#050508`)

### Step 6 — SGP4 Propagation (per animation frame)

For each satellite in each frame, the app uses **satellite.js** to compute position:

```typescript
// 1. Parse TLE into SGP4 model (done once, cached)
const satrec = twoline2satrec(sat.tle1, sat.tle2);

// 2. Each tick: propagate to current simulation time
const posVel = propagate(satrec, simTime);

// 3. Convert ECI → geodetic using Greenwich Sidereal Time
const gst = gstime(simTime);
const geo = eciToGeodetic(posVel.position, gst);

// 4. Convert to longitude/latitude/altitude
const lon = degreesLong(geo.longitude);
const lat = degreesLat(geo.latitude);
const alt = geo.height * 1000;  // km
```

### Step 7 — Cesium Entity Updates (animation loop)

```typescript
const tick = () => {
  // Advance simulation clock
  if (isPlaying) {
    simTime = new Date(simTime.getTime() + delta * playbackSpeed);
    // Auto-rotate globe camera 15°/hour
    cameraLon -= (15 / 3600000) * delta * playbackSpeed;
  }

  // Update Cesium clock for day/night shadow
  viewer.clock.currentTime = Cesium.JulianDate.fromDate(simTime);

  // For each satellite: update or create Cesium point entity
  entity.position = Cesium.Cartesian3.fromDegrees(lon, lat, alt);
  // Selected satellites: yellow, 10px; others: grey, 4px

  requestAnimationFrame(tick);
};
```

### Step 8 — Orbit Trail Rendering

Trails are maintained in a `trailEntitiesRef` map keyed by satellite ID. Selected satellites get a **PolylineGlowMaterialProperty** trail (glowing, 2px wide, accent-colored) that updates each tick alongside the satellite point.

---

## 3. Collision Detection Pipeline

### Step 9 — Collision Pair Selection (`src/components/CollisionView.tsx`)

When the user switches to COLLISION view, a pair of satellites is selected:

```typescript
function pickCollisionPair(satellites: SatelliteData[]) {
  // Prefer Starlink-class (53° inclination) for realistic conjunction
  const candidates = satellites.filter((s) => {
    const inc = parseFloat(s.tle2.substring(8, 16).trim());
    return inc > 50 && inc < 56;
  });
  const pool = candidates.length >= 2 ? candidates : satellites;
  return [pool[0], pool[1]];
}
```

### Step 10 — Web Worker Conjunction Screening (`honeycomb.ai/src/workers/conjunctionWorker.ts`)

All heavy computation is offloaded to a **Web Worker** to avoid blocking the UI thread:

**Input:**
```typescript
interface WorkerInput {
  missionSamples: MissionSample[];  // Pre-propagated mission trajectory
  catalog: TlePair[];               // Full satellite catalog
  thresholdKm: number;              // Detection radius (default 5 km)
  missionAltKm: number;             // Mission orbit altitude
  altBandKm: number;                // Altitude screening band (±50 km)
  currentTimeMs: number;
}
```

**Algorithm (step by step):**

1. **Altitude pre-filter** — discard catalog objects outside `missionAlt ± altBandKm`. This reduces the screening population by ~90%.

2. **SGP4 co-propagation** — for each object passing the filter, propagate it at every mission sample time (60-second intervals) using satellite.js.

3. **TCA detection** — track distance at each timestep; record when distance reaches a minimum (i.e., starts increasing after decreasing):
   ```typescript
   if (range < minRange) {
     minRange = range;
     tcaIdx = i;  // Time of Closest Approach index
   }
   ```

4. **Severity classification:**
   ```typescript
   function severity(km: number): "yellow" | "orange" | "red" {
     if (km < 1) return "red";
     if (km < 5) return "orange";
     return "yellow";
   }
   ```

5. **Probability of Collision (Pc)** — Gaussian model with σ = 0.5 km:
   ```typescript
   Pc = exp(-(d²) / (2 × σ²))
   // At d=1 km: Pc ≈ 13.5%
   // At d=2 km: Pc ≈ 0.3%
   ```

6. **Trajectory extraction** — extract a ±10-sample window around TCA for visualization:
   ```typescript
   const trajStart = Math.max(0, tcaIdx - 10);
   const trajEnd = Math.min(missionSamples.length - 1, tcaIdx + 10);
   ```

**Output:**
```typescript
interface ConjunctionResult {
  name: string;
  missDistance_km: number;
  severity: "yellow" | "orange" | "red";
  relativeVelocity_kms: number;
  Pc: number;
  tcaTime: Date;
  objectTrajectory: { time: Date; pos: Vec3 }[];
  missionTrajectory: { time: Date; pos: Vec3 }[];
}
```

### Step 11 — Conjunction Analysis Engine (`honeycomb.ai/src/lib/orbital-mechanics/conjunctionAnalysis.ts`)

A secondary engine (outside the worker) performs a finer TCA search using **ECI→ECEF frame conversion**:

```typescript
// Detect TCA: distance was below threshold AND is now increasing
if (dist <= warningThresholdKm && dist >= prevDist && prevDist < warningThresholdKm) {
  events.push({
    catalogObject: tle.name,
    time: s.time,
    missDistance_km: prevDist,
    severity: prevDist <= criticalThreshold ? "critical" : "warning",
    relativeVelocity_kms: vecMag(vecSub(ourVel, catVel)),
  });
}
```

---

## 4. Physics-Based Orbital Mechanics (honeycomb.ai)

### RK4 Propagator (`src/lib/orbital-mechanics/physicsOrbit.ts`)

For high-fidelity mission planning (not real-time display), an RK4 integrator propagates state vectors with a **10-second timestep**:

```
pos(t+dt) = pos(t) + (k1 + 2k2 + 2k3 + k4) * dt/6
```

Where each k includes all force contributions:

### Force Models (`src/lib/orbital-mechanics/forceModel.ts`)

| Force | Model | Key Constants |
|-------|-------|---------------|
| Two-body gravity | `a = -MU * r / |r|³` | MU = 398,600.4418 km³/s² |
| J2 oblateness | Zonal harmonic perturbation | J2 = 1.08263e-3, RE = 6378.137 km |
| Atmospheric drag | Exponential density model (7 altitude bands) | Cd, cross-section area |
| Solar radiation pressure | Inverse-square, eclipse shadow check | P_SR = 4.56e-15 N/km² |
| Thrust / maneuvers | Prograde/retrograde/normal/radial burns | Isp, thrust_N, mass_kg |

**Drag acceleration:**
```
F_drag = -0.5 × ρ(h) × Cd × A × |v_rel| × v_rel
```

**Mass flow during burn:**
```
dm/dt = -thrust_N / (Isp × g0)
```

---

## 5. 3D Satellite Close-up Viewer (`src/components/SatelliteCloseupViewer.tsx`)

When a conjunction is detected, each satellite is rendered in a dedicated Cesium viewport as a scaled 3D model:

```typescript
const BODY = { x: 3.0, y: 0.6, z: 0.6 };  // Main bus (meters)
const PANEL = { x: 5.0, y: 0.05, z: 1.6 }; // Solar panel
const PANEL_OFFSET = BODY.x / 2 + PANEL.x / 2 + 0.1;

// Camera: 30° heading, -20° pitch, 30m range
viewer.camera.lookAt(satPos, new Cesium.HeadingPitchRange(
  Cesium.Math.toRadians(30),
  Cesium.Math.toRadians(-20),
  30
));
```

---

## 6. AI Agent Orchestration (honeycomb.ai)

### Agent Chat Interface (`src/components/agent/AgentChat.tsx`)

The AI agent is a **Claude model** served via a Supabase Edge Function:

```typescript
const res = await fetch(`${supabaseUrl}/functions/v1/agent-chat`, {
  method: "POST",
  headers: { Authorization: `Bearer ${supabaseAnonKey}` },
  body: JSON.stringify({ mission_id: activeMission.id, messages: history }),
});

const { reply, updates_applied } = await res.json();

// If agent mutated the DB, reload mission state
if (updates_applied?.length > 0) {
  await loadFromMissionId(activeMission.id);
}
```

**Agent capabilities:**
- Parse CONOPS documents and extract orbital parameters
- Fill in missing TLE/orbital elements (inclination, RAAN, altitude, eccentricity)
- Add ground station networks (e.g., KSAT/SSC polar networks)
- Generate synthetic TLEs from Keplerian elements
- Mutate the Supabase mission database directly

### Agent Logs Panel (`src/components/AgentLogsPanel.tsx`)

In the collision view, three simulated agents stream log entries:

- **AGENT-ALPHA** — Conjunction detection and TCA calculation
- **AGENT-BETA** — Risk assessment and Pc computation
- **AGENT-GAMMA** — Maneuver recommendation and avoidance planning

Logs trickle in every **3 seconds**, auto-scroll to the latest entry, and include a live conjunction summary card showing miss distance, TCA countdown, and severity level.

---

## 7. Full Data Flow

```
[User opens app]
        │
        ▼
GET /api/tle ──► SatNOGS API (or hardcoded fallback)
        │
        ▼
parseTLEText() → SatelliteData[]
        │
        ▼
Zustand satelliteStore
  satellites[], currentTime, isPlaying, playbackSpeed
        │
        ▼
GlobeViewer animation loop (requestAnimationFrame @ 60fps)
  │  twoline2satrec() — parse TLE into SGP4 model (once per satellite)
  │  propagate(satrec, simTime) — ECI position at current time
  │  eciToGeodetic(pos, gstime) — convert to lat/lon/alt
  │  Cesium.Cartesian3.fromDegrees() — update entity position
  └─ Orbit trail updated for selected satellite
        │
        ▼
[User switches to COLLISION view]
        │
        ▼
pickCollisionPair() — select two ~53° inclination satellites
        │
        ▼
Web Worker: conjunctionWorker.ts
  1. Altitude band pre-filter (±50 km)
  2. SGP4 propagate both objects at 60s intervals
  3. Find TCA (minimum range)
  4. Classify severity (red/orange/yellow)
  5. Compute Pc = exp(-d²/2σ²)
  6. Extract ±10-sample trajectory window
        │
        ▼
CollisionView renders:
  ├── AgentLogsPanel (AGENT-ALPHA/BETA/GAMMA streaming logs)
  ├── SatelliteCloseupViewer A (3D model, Cesium)
  └── SatelliteCloseupViewer B (3D model, Cesium)

[Advanced mission planning — honeycomb.ai]
        │
        ▼
RK4 physicsOrbit.ts (10s timestep)
  ├── gravity + J2 + drag + SRP + thrust
  └── PhysicsSample[] (pos, vel, mass per step)
        │
        ▼
conjunctionAnalysis.ts — high-fidelity TCA detection
        │
        ▼
AgentChat → Supabase Edge Function (Claude API)
  ├── Ingest CONOPS, fill missing parameters
  ├── Optimize orbit / maneuvers
  └── DB mutations → reload mission state
```

---

## 8. Key Parameters

### Orbital Mechanics
| Constant | Value | Unit |
|----------|-------|------|
| Earth GM | 398,600.4418 | km³/s² |
| Earth radius | 6,378.137 | km |
| J2 | 1.08263 × 10⁻³ | — |
| Solar radiation constant | 4.56 × 10⁻¹⁵ | N/km² |
| Earth rotation | 7.2921150 × 10⁻⁵ | rad/s |

### Collision Thresholds
| Parameter | Default |
|-----------|---------|
| Warning threshold | 5 km |
| Critical threshold | 1 km |
| Collision probability σ | 0.5 km |
| Altitude screening band | ±50 km |
| TCA trajectory window | ±10 samples (60s each) |

### Simulation
| Parameter | Value |
|-----------|-------|
| Physics timestep | 10 s |
| Conjunction screening interval | 60 s |
| Playback speeds | 1, 10, 60, 300, 1000 × |
| Frame rate | 60 fps |
| Camera auto-rotation | 15°/hour |
| TLE cache TTL | 3600 s |

---

## 9. Technology Stack

**nvidia_hack (frontend)**
- Next.js 13+ / React 18
- Zustand (global state)
- CesiumJS 1.122 (3D globe)
- satellite.js (SGP4/SDP4 propagation)
- Tailwind CSS

**honeycomb.ai (mission planning)**
- Vite + React 18
- Zustand
- Custom RK4 physics engine
- satellite.js
- Supabase (PostgreSQL + Edge Functions)
- Claude API (AI agent)
- Web Workers (conjunction, coverage, drag screening)

**External data sources**
- SatNOGS: `db.satnogs.org/api/tle/`
- CelesTrak: `celestrak.org/NORAD/elements/`
- NASA GIBS: Blue Marble imagery tiles
