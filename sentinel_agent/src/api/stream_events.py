"""Event models for streaming negotiation and LLM outputs."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StreamEventType(str, Enum):
    """Types of events emitted during negotiation."""

    NEGOTIATION_MESSAGE = "negotiation_message"
    LLM_OUTPUT = "llm_output"
    DECISION = "decision"
    SIMULATION_START = "simulation_start"
    SIMULATION_END = "simulation_end"


class LLMStage(str, Enum):
    """LLM reasoning stages that produce structured output."""

    ANALYZE = "analyze"
    PROPOSAL = "proposal"
    EVALUATE_RESPONSE = "evaluate_response"
    EVALUATE_PROPOSAL = "evaluate_proposal"
    DECISION = "decision"


class StreamEvent(BaseModel):
    """Single event emitted to the stream."""

    type: StreamEventType = Field(description="Event type")
    pair_label: str | None = Field(default=None, description="Pair label (e.g. A↔B)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict[str, Any] = Field(default_factory=dict, description="Event payload")
