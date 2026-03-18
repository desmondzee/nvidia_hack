"""Data models for physics agent output — collision alerts and space objects."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Vector3(BaseModel):
    """3D vector in ECI (Earth-Centered Inertial) frame."""

    x: float
    y: float
    z: float


class ThreatLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SpaceObject(BaseModel):
    """Describes one space object (satellite, debris, or rocket body)."""

    object_id: str
    object_name: str
    object_type: str = Field(description="satellite, debris, or rocket_body")
    position: Vector3 = Field(description="Current position in km (ECI frame)")
    velocity: Vector3 = Field(description="Current velocity in km/s (ECI frame)")
    covariance_diagonal: Vector3 | None = Field(
        default=None, description="Simplified position uncertainty (km)"
    )


class CollisionAlert(BaseModel):
    """
    Primary input from the physics agent to the negotiation agent.
    Modeled after a simplified Conjunction Data Message (CDM).
    """

    alert_id: str
    time_of_closest_approach: datetime = Field(description="TCA timestamp")
    our_object: SpaceObject
    threat_object: SpaceObject
    miss_distance_m: float = Field(description="Predicted miss distance in meters")
    probability_of_collision: float = Field(
        ge=0.0, le=1.0, description="Pc, 0.0 to 1.0"
    )
    threat_level: ThreatLevel
    relative_velocity: Vector3 = Field(description="Relative velocity at TCA (km/s)")
    time_to_tca_seconds: float = Field(description="Seconds until closest approach")
    weather_parameters: dict | None = Field(
        default=None, description="Solar activity, drag coefficients, etc."
    )
    raw_cdm_data: dict | None = Field(
        default=None, description="Pass-through for extra CDM fields"
    )
