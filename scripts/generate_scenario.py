"""
Synthetic data generation pipeline for the hero collision demo.

Pipeline:
  1. Pull REAL orbital + space weather data from the running satellite API
  2. Send that as grounding context to Nemotron on the DGX Spark (via Ollama)
  3. LLM generates physically-consistent synthetic CDMs for 4 escalation steps
  4. Output saved to satellite_traffic_api/scenarios/hero_collision.json

The scenario JSON is then loaded by ScenarioAdapter at runtime, replacing
the Space-Track conjunction adapter with synthetic data that is grounded
in real orbital mechanics.

Usage:
    # Make sure the satellite API is running first:
    uvicorn satellite_traffic_api.main:app --port 8000

    # Then generate — points at Nemotron on your DGX Spark:
    python scripts/generate_scenario.py

    # Or override defaults:
    python scripts/generate_scenario.py \\
        --api-url http://localhost:8000 \\
        --ollama-url http://10.1.96.155:8080 \\
        --model nemotron-nano-30b
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Install httpx: uv pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# The two real satellites for the demo
# ---------------------------------------------------------------------------
PRIMARY_NORAD = 25544    # ISS
SECONDARY_NORAD = 44714  # STARLINK-1008 (confirmed active)


def _safe_get(client: httpx.Client, url: str) -> dict:
    """GET with graceful fallback on any error."""
    try:
        resp = client.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"  WARNING: {url} failed — {exc}")
        return {}


def fetch_real_context(api_url: str) -> dict:
    """Pull live orbital + space weather data from the running satellite API."""
    base = api_url.rstrip("/")
    print("Fetching real data from satellite API...")

    with httpx.Client(timeout=30) as client:
        iss_tle   = _safe_get(client, f"{base}/v1/satellites/{PRIMARY_NORAD}/tle")
        iss_state = _safe_get(client, f"{base}/v1/satellites/{PRIMARY_NORAD}/state")
        sl_tle    = _safe_get(client, f"{base}/v1/satellites/{SECONDARY_NORAD}/tle")
        sl_state  = _safe_get(client, f"{base}/v1/satellites/{SECONDARY_NORAD}/state")
        wx        = _safe_get(client, f"{base}/v1/space-weather/current")

    def _fmt(v):
        try:
            return f"{float(v):.1f}"
        except (TypeError, ValueError):
            return "?"

    print(f"  ISS (NORAD {PRIMARY_NORAD}):      "
          f"alt={_fmt(iss_state.get('altitude_km'))} km  "
          f"inc={iss_tle.get('inclination_deg', '?')}°")
    print(f"  Starlink (NORAD {SECONDARY_NORAD}): "
          f"alt={_fmt(sl_state.get('altitude_km'))} km  "
          f"inc={sl_tle.get('inclination_deg', '?')}°")
    print(f"  Space wx: Kp={wx.get('current_kp', '?')}  storm={wx.get('storm_level', '?')}")

    if not iss_tle or not iss_state:
        print("\nERROR: Could not fetch ISS data. Is the satellite API running?")
        print(f"  Start it with: uvicorn satellite_traffic_api.main:app --port 8000")
        raise SystemExit(1)

    return {
        "iss": {"tle": iss_tle, "state": iss_state},
        "starlink": {"tle": sl_tle, "state": sl_state},
        "space_weather": wx,
    }


def build_prompt(real: dict) -> str:
    iss   = real["iss"]
    sl    = real["starlink"]
    wx    = real["space_weather"]

    # Compute approximate altitude difference and inclination spread
    alt_diff  = abs(iss["state"].get("altitude_km", 420) - sl["state"].get("altitude_km", 425))
    inc_diff  = abs(iss["tle"].get("inclination_deg", 51.6) - sl["tle"].get("inclination_deg", 53.0))
    kp        = wx.get("current_kp", 2)
    drag_enh  = wx.get("atmospheric_drag_enhancement_factor", 1.0)

    return f"""You are a space domain awareness system generating synthetic Conjunction Data Messages (CDMs).

REAL ORBITAL DATA (use these exact values as your baseline):

ISS (NORAD 25544):
  altitude_km:       {iss["state"].get("altitude_km", 420.5):.2f}
  inclination_deg:   {iss["tle"].get("inclination_deg", 51.64)}
  speed_km_s:        {iss["state"].get("speed_km_s", 7.66):.4f}
  latitude_deg:      {iss["state"].get("latitude_deg", 0):.2f}
  longitude_deg:     {iss["state"].get("longitude_deg", 0):.2f}

STARLINK-1007 (NORAD 44713):
  altitude_km:       {sl["state"].get("altitude_km", 424.8):.2f}
  inclination_deg:   {sl["tle"].get("inclination_deg", 53.05)}
  speed_km_s:        {sl["state"].get("speed_km_s", 7.64):.4f}

Current altitude difference: {alt_diff:.2f} km
Inclination spread:          {inc_diff:.2f} degrees

CURRENT SPACE WEATHER:
  Kp index:          {kp}
  Storm level:       {wx.get("storm_level", "NONE")}
  Drag enhancement:  {drag_enh:.2f}x baseline

TASK:
Generate a 4-step conjunction escalation scenario where these two satellites have a near-collision
that is subsequently resolved by a maneuver. The scenario must be physically consistent with the
real orbital data above.

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation):

{{
  "scenario_id": "hero_collision",
  "description": "ISS and Starlink-1007 near-collision — 4-step escalation and resolution",
  "generated_from_real_data": true,
  "satellites": {{
    "primary": {{
      "norad_id": 25544,
      "name": "ISS (ZARYA)",
      "altitude_km": {iss["state"].get("altitude_km", 420.5):.2f},
      "inclination_deg": {iss["tle"].get("inclination_deg", 51.64)},
      "speed_km_s": {iss["state"].get("speed_km_s", 7.66):.4f},
      "operator": "ISS Program / Multi-national"
    }},
    "secondary": {{
      "norad_id": 44713,
      "name": "STARLINK-1007",
      "altitude_km": {sl["state"].get("altitude_km", 424.8):.2f},
      "inclination_deg": {sl["tle"].get("inclination_deg", 53.05)},
      "speed_km_s": {sl["state"].get("speed_km_s", 7.64):.4f},
      "operator": "SpaceX"
    }}
  }},
  "steps": [
    {{
      "step": 1,
      "label": "NOMINAL",
      "risk_level": "NOMINAL",
      "tca_minutes_from_now": 95,
      "miss_distance_km": FILL_IN (30-50 km, routine pass),
      "collision_probability": null,
      "relative_speed_km_s": FILL_IN (consistent with inclination spread of {inc_diff:.2f} deg, expect 7-14 km/s),
      "radial_miss_m": FILL_IN,
      "in_track_miss_m": FILL_IN,
      "cross_track_miss_m": FILL_IN (sqrt of sum of squares must equal miss_distance_km * 1000),
      "narrative": "FILL_IN (1 sentence, routine pass no concern)"
    }},
    {{
      "step": 2,
      "label": "HIGH",
      "risk_level": "HIGH",
      "tca_minutes_from_now": 68,
      "miss_distance_km": FILL_IN (0.6-1.0 km),
      "collision_probability": FILL_IN (1e-5 to 9e-5),
      "relative_speed_km_s": FILL_IN (same as step 1 — same geometry),
      "radial_miss_m": FILL_IN,
      "in_track_miss_m": FILL_IN,
      "cross_track_miss_m": FILL_IN,
      "narrative": "FILL_IN (1 sentence, updated track tightens conjunction)"
    }},
    {{
      "step": 3,
      "label": "CRITICAL",
      "risk_level": "CRITICAL",
      "tca_minutes_from_now": 24,
      "miss_distance_km": FILL_IN (0.1-0.25 km),
      "collision_probability": FILL_IN (5e-4 to 1e-3),
      "relative_speed_km_s": FILL_IN (same as step 1),
      "radial_miss_m": FILL_IN,
      "in_track_miss_m": FILL_IN,
      "cross_track_miss_m": FILL_IN,
      "narrative": "FILL_IN (1 sentence, final track confirms critical threat)"
    }},
    {{
      "step": 4,
      "label": "RESOLVED",
      "risk_level": "NOMINAL",
      "tca_minutes_from_now": 0,
      "miss_distance_km": FILL_IN (14-22 km, post-maneuver),
      "collision_probability": null,
      "relative_speed_km_s": FILL_IN (same as step 1),
      "radial_miss_m": FILL_IN (large — ISS moved radially),
      "in_track_miss_m": FILL_IN,
      "cross_track_miss_m": FILL_IN,
      "narrative": "FILL_IN (1 sentence, ISS burn executed, threat cleared)"
    }}
  ],
  "maneuver": {{
    "executing_satellite": "ISS (ZARYA)",
    "maneuver_type": "posigrade burn",
    "delta_v_m_s": FILL_IN (0.5-2.0, real ISS avoidance burns),
    "burn_duration_seconds": FILL_IN (consistent with delta_v and ISS thruster specs ~0.9 N),
    "altitude_change_km": FILL_IN (small positive, consistent with delta_v),
    "executed_at_minutes_before_tca": 22
  }}
}}

Physics constraints:
- relative_speed_km_s MUST be identical across all steps (same orbital geometry, only tracking uncertainty changes)
- Each miss distance vector (radial, in-track, cross-track) must satisfy: sqrt(r^2 + i^2 + c^2) = miss_distance_km * 1000 (meters)
- Kp={kp} means drag enhancement of {drag_enh:.2f}x — mention this in the step 1 narrative if Kp > 3
- delta_v and burn_duration must be physically consistent (ISS thrusters: ~890N total, mass ~420,000 kg)
"""


def check_spark(spark_url: str, model: str) -> None:
    """Verify the DGX Spark llama.cpp server is reachable and has the model."""
    try:
        resp = httpx.get(f"{spark_url.rstrip('/')}/v1/models", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Support both {models:[]} and {data:[]} response shapes
        entries = data.get("models") or data.get("data") or []
        available = [m.get("name") or m.get("id") for m in entries]
    except Exception as exc:
        print(f"\nERROR: Cannot reach DGX Spark at {spark_url} — {exc}")
        raise SystemExit(1)

    if not any(model in (m or "") for m in available):
        print(f"\nModel '{model}' not found on Spark.")
        print(f"Available: {available or 'none'}")
        raise SystemExit(1)

    print(f"  DGX Spark ready — model '{model}' available")


def generate(spark_url: str, model: str, prompt: str) -> dict:
    """Call the llama.cpp OpenAI-compatible endpoint on the DGX Spark."""
    url = f"{spark_url.rstrip('/')}/v1/chat/completions"
    print(f"Sending to DGX Spark at {spark_url} (model: {model}) ...")

    with httpx.Client(timeout=300) as client:
        resp = client.post(url, json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a space domain awareness data generator. "
                        "Output only valid JSON. No markdown fences. No explanation text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 8192,   # Reasoning model needs room to think + produce JSON
        })
        resp.raise_for_status()

    body = resp.json()
    msg = body["choices"][0]["message"]
    print(f"  Tokens used: {body.get('usage', {}).get('total_tokens', '?')}")

    # Nemotron reasoning model: final answer in content, chain-of-thought in reasoning_content
    raw = (msg.get("content") or "").strip()

    # If content is empty the JSON is embedded in reasoning_content — extract it
    if not raw:
        reasoning = (msg.get("reasoning_content") or "")
        # Pull the outermost JSON object from the reasoning text
        start = reasoning.find("{")
        end   = reasoning.rfind("}") + 1
        if start != -1 and end > start:
            raw = reasoning[start:end]
        else:
            print("\nDEBUG — raw model output:")
            print(reasoning[:2000])
            raise ValueError("Could not find JSON in model output")

    # Strip markdown fences as a last resort
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())


def validate(scenario: dict) -> list[str]:
    """Basic physics validation on the generated scenario."""
    import math
    warnings = []
    steps = scenario.get("steps", [])

    # Check relative_speed consistency
    speeds = [s.get("relative_speed_km_s") for s in steps if s.get("relative_speed_km_s")]
    if speeds and (max(speeds) - min(speeds)) > 1.0:
        warnings.append(f"relative_speed_km_s varies across steps: {speeds} — should be constant")

    # Check miss distance vector consistency
    for s in steps:
        r = s.get("radial_miss_m", 0) or 0
        i = s.get("in_track_miss_m", 0) or 0
        c = s.get("cross_track_miss_m", 0) or 0
        expected_m = (s.get("miss_distance_km") or 0) * 1000
        actual_m = math.sqrt(r**2 + i**2 + c**2)
        if expected_m > 0 and abs(actual_m - expected_m) / expected_m > 0.15:
            warnings.append(
                f"Step {s['step']}: miss distance vector {actual_m:.0f}m "
                f"doesn't match miss_distance_km ({expected_m:.0f}m)"
            )

    return warnings


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic collision scenario grounded in real satellite data"
    )
    parser.add_argument("--api-url",    default="http://localhost:8001",   help="Running satellite API URL")
    parser.add_argument("--ollama-url", default="http://10.1.96.155:8080", help="DGX Spark llama.cpp server URL")
    parser.add_argument("--model",      default="nemotron-nano-30b",        help="Model name")
    parser.add_argument("--out",        default="satellite_traffic_api/scenarios/hero_collision.json")
    parser.add_argument("--dry-run",    action="store_true", help="Print prompt only, don't call Ollama")
    args = parser.parse_args()

    # Step 1: Pull real data from your running satellite API
    real = fetch_real_context(args.api_url)

    # Step 2: Build grounded prompt with real orbital values substituted in
    prompt = build_prompt(real)

    if args.dry_run:
        print("\n--- PROMPT (what gets sent to Nemotron) ---")
        print(prompt)
        return

    # Step 3: Verify Spark + model are ready
    check_spark(args.ollama_url, args.model)

    # Step 4: Generate via Nemotron on DGX Spark
    scenario = generate(args.ollama_url, args.model, prompt)

    # Step 4: Stamp provenance
    scenario["generated_at"] = datetime.now(timezone.utc).isoformat()
    scenario["grounded_from"] = {
        "iss_altitude_km":      real["iss"]["state"].get("altitude_km"),
        "starlink_altitude_km": real["starlink"]["state"].get("altitude_km"),
        "space_weather_kp":     real["space_weather"].get("current_kp"),
        "api_url":              args.api_url,
    }

    # Step 5: Validate physics
    warnings = validate(scenario)
    if warnings:
        print("\nPhysics warnings (review before demo):")
        for w in warnings:
            print(f"  ⚠  {w}")
    else:
        print("Physics validation passed.")

    # Step 6: Write output
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scenario, indent=2))

    print(f"\nScenario written to {out_path}")
    print(f"  Steps:    {len(scenario.get('steps', []))}")
    print(f"  Maneuver: {scenario.get('maneuver', {}).get('delta_v_m_s')} m/s delta-v")


if __name__ == "__main__":
    main()
