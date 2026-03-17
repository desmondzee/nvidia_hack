"""Data models for the negotiation protocol between satellite agents."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from src.models.physics import Vector3


class NegotiationPhase(str, Enum):
    PROPOSAL = "proposal"
    RESPONSE = "response"


class ProposalType(str, Enum):
    MANEUVER_REQUEST = "maneuver_request"
    MANEUVER_OFFER = "maneuver_offer"
    SHARED_MANEUVER = "shared_maneuver"


class SharedCollisionData(BaseModel):
    """
    Subset of collision data chosen to share with the peer satellite.
    The negotiation agent (LLM) decides what goes here — sensitive data
    like exact covariance or internal capabilities may be withheld.
    """

    alert_id: str
    time_of_closest_approach: datetime
    miss_distance_m: float
    probability_of_collision: float
    threat_level: str
    our_object_id: str
    our_planned_position: Vector3 | None = None
    relative_velocity_magnitude: float | None = None


class ProposedManeuver(BaseModel):
    """A proposed avoidance maneuver."""

    delta_v: Vector3 = Field(description="Change in velocity (m/s, RTN frame)")
    burn_start_time: datetime
    burn_duration_seconds: float
    expected_miss_distance_after_m: float = Field(
        description="Predicted miss distance post-maneuver"
    )
    fuel_cost_estimate: float | None = Field(
        default=None, description="Estimated propellant cost in kg"
    )


class NegotiationMessage(BaseModel):
    """
    Wire message exchanged between two negotiation agents.
    Used for proposals and responses across up to 3 negotiation rounds.
    """

    message_id: str
    session_id: str = Field(description="Links all messages in a negotiation session")
    round_number: int = Field(ge=1, le=3, description="Current negotiation round")
    phase: NegotiationPhase
    sender_satellite_id: str
    receiver_satellite_id: str
    timestamp: datetime

    collision_data: SharedCollisionData
    proposal_type: ProposalType
    proposed_maneuver: ProposedManeuver | None = None
    reasoning: str = Field(description="LLM-generated explanation of the proposal")
    accepted: bool | None = Field(
        default=None, description="Set in RESPONSE phase only"
    )
    counter_proposal: ProposedManeuver | None = Field(
        default=None, description="Alternative maneuver if rejecting"
    )
