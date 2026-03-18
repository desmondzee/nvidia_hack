"""
ScenarioAdapter — drops in as a replacement for SpaceTrackAdapter.
Serves synthetic CDM data from a pre-generated scenario JSON file.
The current demo step is controlled via the ScenarioState singleton.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .base import BaseAdapter
from satellite_traffic_api.cache.backend import CacheBackend
from satellite_traffic_api.config import Settings
from satellite_traffic_api.models.conjunction import ConjunctionEvent
from satellite_traffic_api.scenarios.loader import load_scenario

logger = logging.getLogger(__name__)


class ScenarioState:
    """Mutable singleton tracking the current demo step."""
    _instance: ScenarioState | None = None

    def __init__(self) -> None:
        self.current_step: int = 1

    @classmethod
    def get(cls) -> ScenarioState:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def advance(self) -> int:
        self.current_step += 1
        return self.current_step

    def reset(self) -> None:
        self.current_step = 1


class ScenarioAdapter(BaseAdapter[list[ConjunctionEvent]]):
    """
    Reads synthetic conjunction data from a scenario JSON file.
    Implements the same interface as SpaceTrackAdapter so it can be
    swapped in transparently at the context builder level.
    """

    def __init__(self, settings: Settings, cache: CacheBackend, scenario_id: str) -> None:
        super().__init__(settings, cache)
        self.scenario_id = scenario_id
        self._state = ScenarioState.get()

    @property
    def ttl_seconds(self) -> int:
        return 10  # Short TTL so step advances are picked up quickly

    def cache_key(self, **kwargs) -> str:
        return f"scenario:{self.scenario_id}:step:{self._state.current_step}:{kwargs.get('norad_id')}"

    async def fetch_raw(self, **kwargs) -> Any:
        scenario = load_scenario(self.scenario_id)
        step = self._state.current_step
        steps = {s["step"]: s for s in scenario.get("steps", [])}
        if step not in steps:
            logger.warning("Scenario step %d not found, defaulting to step 1", step)
            step = 1
        return {
            "step_data": steps[step],
            "scenario": scenario,
            "norad_id": kwargs.get("norad_id"),
        }

    def normalize(self, raw: Any, **kwargs) -> list[ConjunctionEvent]:
        if not isinstance(raw, dict) or "step_data" not in raw:
            return []

        s = raw["step_data"]
        scenario = raw["scenario"]
        norad_id = raw.get("norad_id", 0)
        now = datetime.now(timezone.utc)

        # No threat at nominal or resolved steps
        if s["risk_level"] == "NOMINAL":
            return []

        secondary = scenario["satellites"]["secondary"]
        tca = now + timedelta(minutes=s["tca_minutes_from_now"])

        return [
            ConjunctionEvent(
                event_id=f"{self.scenario_id}_step{s['step']}",
                tca=tca,
                miss_distance_km=s["miss_distance_km"],
                collision_probability=s.get("collision_probability"),
                relative_speed_km_s=s.get("relative_speed_km_s"),
                primary_norad_id=norad_id,
                secondary_norad_id=secondary["norad_id"],
                secondary_object_name=secondary["name"],
                secondary_object_type="PAYLOAD",
                cdm_source="SPACETRACK",
                days_until_tca=s["tca_minutes_from_now"] / 1440,
            )
        ]

    async def get_conjunctions(self, norad_id: int) -> list[ConjunctionEvent]:
        return await self.get(norad_id=norad_id)
