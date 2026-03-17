"""Pydantic models for the negotiation memory service."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Vector3(BaseModel):
    x: float
    y: float
    z: float


class ProposedManeuver(BaseModel):
    delta_v: Vector3
    burn_start_time: datetime
    burn_duration_seconds: float
    expected_miss_distance_after_m: float
    fuel_cost_estimate: float | None = None


class NegotiationRound(BaseModel):
    """A single round of proposal/response in a negotiation."""

    round_number: int
    initiator_proposal: str = Field(description="LLM reasoning from the initiator")
    responder_response: str = Field(description="LLM reasoning from the responder")
    initiator_proposed_maneuver: ProposedManeuver | None = None
    responder_counter_proposal: ProposedManeuver | None = None
    accepted_this_round: bool


class StoreNegotiationRequest(BaseModel):
    """Request to store a completed negotiation session."""

    session_id: str
    alert_id: str
    initiator_satellite_id: str
    responder_satellite_id: str

    # Collision parameters
    miss_distance_m: float
    probability_of_collision: float
    time_of_closest_approach: datetime
    threat_level: str
    relative_velocity_m_s: float | None = None

    # Context at time of negotiation
    space_weather_kp: float | None = None
    atmospheric_drag_factor: float | None = None

    # Conversation
    rounds: list[NegotiationRound]
    final_agreed: bool
    final_initiator_maneuver: ProposedManeuver | None = None
    final_responder_maneuver: ProposedManeuver | None = None
    negotiation_summary: str
    rounds_taken: int

    negotiated_at: datetime = Field(default_factory=datetime.utcnow)

    # Optional free-form tags for retrieval
    tags: list[str] = Field(default_factory=list)
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


class StoreDocumentRequest(BaseModel):
    """Store an arbitrary informational document (policy, manual, space law, etc.)."""

    document_id: str
    title: str
    content: str
    category: str = Field(
        description="e.g. 'policy', 'maneuver_guide', 'space_law', 'historical_event'"
    )
    tags: list[str] = Field(default_factory=list)


class RetrieveRequest(BaseModel):
    """Query historical memory for relevant context."""

    query: str = Field(
        description="Natural language description of the current situation"
    )
    satellite_ids: list[str] = Field(
        default_factory=list,
        description="Filter results that involve any of these satellite IDs",
    )
    n_results: int = Field(default=5, ge=1, le=20)
    min_similarity: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum cosine similarity threshold"
    )
    include_documents: bool = Field(
        default=True, description="Include informational documents in results"
    )
    include_negotiations: bool = Field(
        default=True, description="Include past negotiation sessions in results"
    )


class MemoryEntry(BaseModel):
    """A single retrieved memory entry."""

    entry_id: str
    entry_type: str  # "negotiation" | "document"
    similarity_score: float
    summary: str
    full_text: str
    metadata: dict[str, Any]


class RetrieveResponse(BaseModel):
    results: list[MemoryEntry]
    total_found: int
    query_used: str


class SatelliteHistoryResponse(BaseModel):
    satellite_id: str
    total_negotiations: int
    agreed_count: int
    negotiations: list[dict[str, Any]]
