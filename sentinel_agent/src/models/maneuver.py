"""Data model for the final agreed-upon maneuver decision."""

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.negotiation import ProposedManeuver


class ManeuverDecision(BaseModel):
    """Final output after negotiation completes."""

    session_id: str
    alert_id: str
    our_satellite_id: str
    peer_satellite_id: str
    agreed: bool = Field(description="Whether both parties reached agreement")
    our_maneuver: ProposedManeuver | None = None
    peer_maneuver: ProposedManeuver | None = None
    negotiation_summary: str
    rounds_taken: int = Field(ge=1, le=3)
    decided_at: datetime
