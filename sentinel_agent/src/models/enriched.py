"""Mirror of satellite_traffic_api's EnrichedCollisionAlert.

This model validates the JSON payload arriving at the sentinel_agent's
/negotiate endpoint and provides a to_collision_alert() conversion so
the existing negotiation graph (which expects CollisionAlert) can be
used unchanged.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.physics import CollisionAlert, SpaceObject, ThreatLevel, Vector3


class EciVector(BaseModel):
    """3-axis ECI vector — matches satellite_traffic_api's EciVector."""
    x: float
    y: float
    z: float


class SpaceObjectPayload(BaseModel):
    """Space object with full ECI state at TCA."""
    object_id: str
    object_name: str
    object_type: str
    position_km: EciVector
    velocity_km_s: EciVector
    covariance_diagonal_km: EciVector | None = None

    def to_space_object(self) -> SpaceObject:
        cov = (
            Vector3(
                x=self.covariance_diagonal_km.x,
                y=self.covariance_diagonal_km.y,
                z=self.covariance_diagonal_km.z,
            )
            if self.covariance_diagonal_km
            else None
        )
        return SpaceObject(
            object_id=self.object_id,
            object_name=self.object_name,
            object_type=self.object_type,
            position=Vector3(
                x=self.position_km.x,
                y=self.position_km.y,
                z=self.position_km.z,
            ),
            velocity=Vector3(
                x=self.velocity_km_s.x,
                y=self.velocity_km_s.y,
                z=self.velocity_km_s.z,
            ),
            covariance_diagonal=cov,
        )


class ConjunctionSummary(BaseModel):
    """Compact summary of a secondary conjunction for multi-threat awareness."""
    event_id: str
    tca: datetime
    miss_distance_km: float
    collision_probability: float | None
    secondary_object_name: str
    secondary_object_type: str


class EnrichedCollisionAlert(BaseModel):
    """
    Integration bridge payload from satellite_traffic_api.

    Superset of CollisionAlert. Contains full orbital + environmental context
    so the negotiation LLM can make holistic maneuver decisions.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    alert_id: str
    generated_at: datetime
    cdm_source: str

    # ── Core conjunction ──────────────────────────────────────────────────────
    time_of_closest_approach: datetime
    time_to_tca_seconds: float
    miss_distance_m: float
    probability_of_collision: float = Field(ge=0.0, le=1.0)
    relative_velocity_km_s: EciVector

    # ── Space objects at TCA ──────────────────────────────────────────────────
    our_object: SpaceObjectPayload
    threat_object: SpaceObjectPayload

    # ── Threat level ──────────────────────────────────────────────────────────
    threat_level: str                           # "low"|"medium"|"high"|"critical"

    # ── Risk classification detail ────────────────────────────────────────────
    rule_based_risk: str
    ml_risk: str
    final_risk: str
    recommended_action: str

    # ── Space weather ─────────────────────────────────────────────────────────
    weather_parameters: dict

    # ── Atmospheric state ─────────────────────────────────────────────────────
    atmospheric_density_kg_m3: float | None = None
    atmospheric_drag_acceleration_m_s2: float | None = None

    # ── Multi-threat awareness ────────────────────────────────────────────────
    total_active_conjunctions: int
    other_high_risk_conjunctions: list[ConjunctionSummary] = []

    # ── Ground contact ────────────────────────────────────────────────────────
    minutes_to_next_ground_contact: float | None = None
    next_ground_station_name: str | None = None

    # ── Provenance ────────────────────────────────────────────────────────────
    data_freshness: dict[str, str] = {}
    raw_conjunction_data: dict = {}

    def to_collision_alert(self) -> CollisionAlert:
        """Convert to sentinel_agent's CollisionAlert for the negotiation graph."""
        try:
            threat_level = ThreatLevel(self.threat_level)
        except ValueError:
            threat_level = ThreatLevel.HIGH

        return CollisionAlert(
            alert_id=self.alert_id,
            time_of_closest_approach=self.time_of_closest_approach,
            our_object=self.our_object.to_space_object(),
            threat_object=self.threat_object.to_space_object(),
            miss_distance_m=self.miss_distance_m,
            probability_of_collision=self.probability_of_collision,
            threat_level=threat_level,
            relative_velocity=Vector3(
                x=self.relative_velocity_km_s.x,
                y=self.relative_velocity_km_s.y,
                z=self.relative_velocity_km_s.z,
            ),
            time_to_tca_seconds=self.time_to_tca_seconds,
            weather_parameters=self.weather_parameters,
            raw_cdm_data=self.raw_conjunction_data or None,
        )
