"""Integration bridge schema: satellite_traffic_api → sentinel_agent.

EnrichedCollisionAlert is a superset of sentinel_agent's CollisionAlert. It
carries full environmental and orbital context so the negotiation agent can
make holistic maneuver decisions without needing a second round-trip.

Field naming conventions:
  - position/velocity fields use the same axis names as sentinel_agent's
    Vector3 (x, y, z) for direct JSON compatibility.
  - Units are km and km/s throughout (sentinel_agent convention).
  - miss_distance_m is in metres (sentinel_agent convention).
"""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class EciVector(BaseModel):
    """3-axis ECI vector (km or km/s). Field names match sentinel_agent's Vector3."""
    model_config = ConfigDict(frozen=True)
    x: float
    y: float
    z: float


class SpaceObjectPayload(BaseModel):
    """Space object with full orbital state at TCA, for use by the negotiation agent."""
    model_config = ConfigDict(frozen=True)

    object_id: str
    object_name: str
    object_type: str                            # "satellite" | "debris" | "rocket_body"
    position_km: EciVector                      # ECI position at TCA (km)
    velocity_km_s: EciVector                    # ECI velocity at TCA (km/s)
    covariance_diagonal_km: EciVector | None = None  # Position uncertainty (km), if known


class ConjunctionSummary(BaseModel):
    """Compact summary of a secondary conjunction for multi-threat awareness."""
    model_config = ConfigDict(frozen=True)

    event_id: str
    tca: datetime
    miss_distance_km: float
    collision_probability: float | None
    secondary_object_name: str
    secondary_object_type: str


class EnrichedCollisionAlert(BaseModel):
    """
    Bridge payload from satellite_traffic_api to sentinel_agent negotiation.

    Contains everything the LLM negotiation agent needs for a holistic decision:
    - Core conjunction data (mirrors sentinel_agent's CollisionAlert fields)
    - Full ECI state vectors for both objects at TCA (from SGP4 propagation)
    - Space weather: geomagnetic storm level, F10.7, atmospheric drag enhancement
    - Atmospheric density at our current altitude (affects maneuver timing)
    - Multi-threat picture: all active conjunctions, not just the worst one
    - Ground station contact window (for planning when to uplink a maneuver command)
    - Dual risk scores: rule-based hard thresholds + XGBoost interaction model
    """
    model_config = ConfigDict(frozen=True)

    # ── Identity ─────────────────────────────────────────────────────────────
    alert_id: str                               # Derived from conjunction event_id
    generated_at: datetime
    cdm_source: str                             # "SPACETRACK" | "CELESTRAK"

    # ── Core conjunction (direct map to sentinel_agent's CollisionAlert) ──────
    time_of_closest_approach: datetime
    time_to_tca_seconds: float
    miss_distance_m: float                      # conjunction.miss_distance_km * 1000
    probability_of_collision: float             # 0.0 when CDM lacks Pc
    relative_velocity_km_s: EciVector           # v_threat − v_our at TCA (km/s)

    # ── Space objects at TCA ─────────────────────────────────────────────────
    our_object: SpaceObjectPayload              # Propagated from our TLE to TCA
    threat_object: SpaceObjectPayload           # Propagated from secondary TLE to TCA

    # ── Threat level (sentinel_agent ThreatLevel enum values) ────────────────
    threat_level: str                           # "low" | "medium" | "high" | "critical"

    # ── Risk classification detail ────────────────────────────────────────────
    rule_based_risk: str                        # NOMINAL | ELEVATED | HIGH | CRITICAL
    ml_risk: str                                # XGBoost prediction (same scale)
    final_risk: str                             # max(rule_based_risk, ml_risk)
    recommended_action: str                     # Human-readable directive

    # ── Space weather context ─────────────────────────────────────────────────
    # Matches the weather_parameters dict that sentinel_agent's CollisionAlert accepts
    weather_parameters: dict                    # keys: kp_index, kp_24h_max,
                                                #   storm_level, solar_flux_f10_7,
                                                #   f107_81day_avg, ap_daily,
                                                #   atmospheric_drag_enhancement_factor,
                                                #   active_alerts

    # ── Atmospheric state at our current altitude ─────────────────────────────
    # Affects drag uncertainty in TCA predictions and maneuver delta-V sizing
    atmospheric_density_kg_m3: float | None
    atmospheric_drag_acceleration_m_s2: float | None

    # ── Multi-threat awareness ────────────────────────────────────────────────
    total_active_conjunctions: int
    other_high_risk_conjunctions: list[ConjunctionSummary]  # Excluding this event

    # ── Ground station contact (for maneuver uplink planning) ─────────────────
    minutes_to_next_ground_contact: float | None
    next_ground_station_name: str | None

    # ── Data provenance ───────────────────────────────────────────────────────
    data_freshness: dict[str, str]              # source → ISO timestamp
    raw_conjunction_data: dict                  # Full ConjunctionEvent.model_dump()
