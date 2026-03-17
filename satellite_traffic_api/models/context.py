from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict

from .orbital import TLERecord, StateVector
from .conjunction import ConjunctionEvent
from .space_weather import SpaceWeatherSummary
from .atmosphere import AtmosphericState
from .ground_station import VisibilityWindow

RiskLevel = Literal["NOMINAL", "ELEVATED", "HIGH", "CRITICAL"]


class SatelliteContext(BaseModel):
    """
    Master aggregated payload for a satellite agent.
    Single call gives the agent everything it needs for traffic negotiation decisions.
    """
    model_config = ConfigDict(frozen=True)

    # Identity
    norad_cat_id: int
    object_name: str
    fetched_at: datetime
    context_valid_until: datetime   # When the agent should refresh

    # Own orbit
    tle: TLERecord
    current_state: StateVector
    orbit_next_24h: list[StateVector] = []   # Hourly positions

    # Threat picture
    conjunctions: list[ConjunctionEvent] = []         # All, sorted by TCA
    high_risk_conjunctions: list[ConjunctionEvent] = []  # miss_dist < 1km or prob > 1e-4

    # Environment
    space_weather: SpaceWeatherSummary
    atmospheric_state: AtmosphericState | None = None

    # Ground connectivity
    upcoming_ground_contacts: list[VisibilityWindow] = []

    # Nearby objects within configured radius
    nearby_object_ids: list[int] = []       # NORAD IDs of nearby objects
    nearby_object_names: list[str] = []

    # Agent-facing risk summary
    collision_risk_level: RiskLevel = "NOMINAL"
    recommended_action: str = ""

    # Per-source freshness timestamps
    data_freshness: dict[str, str] = {}     # source -> ISO timestamp

    # Extensible field for future data sources
    extensions: dict[str, Any] = {}
