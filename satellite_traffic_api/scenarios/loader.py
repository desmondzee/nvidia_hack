from __future__ import annotations
import json
from pathlib import Path
from functools import lru_cache

_SCENARIOS_DIR = Path(__file__).parent


@lru_cache(maxsize=16)
def load_scenario(scenario_id: str) -> dict:
    path = _SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario '{scenario_id}' not found. Run scripts/generate_scenario.py first.")
    return json.loads(path.read_text())


def get_scenario_step(scenario_id: str, step: int) -> dict:
    scenario = load_scenario(scenario_id)
    steps = scenario.get("steps", [])
    matches = [s for s in steps if s["step"] == step]
    if not matches:
        raise ValueError(f"Step {step} not found in scenario '{scenario_id}'")
    return {**scenario, "current_step": matches[0]}
