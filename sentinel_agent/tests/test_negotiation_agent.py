"""Tests for negotiation agent graphs using a mock LLM."""

import asyncio
import json
from datetime import datetime, timezone

import pytest

from src.agents.negotiation_agent import (
    AnalysisOutput,
    DecisionOutput,
    EvaluationOutput,
    ProposalOutput,
    build_initiator_graph,
    build_responder_graph,
    make_initiator_state,
    make_responder_state,
)
from src.models.negotiation import (
    NegotiationMessage,
    NegotiationPhase,
    ProposalType,
    ProposedManeuver,
    SharedCollisionData,
)
from src.models.physics import CollisionAlert, SpaceObject, ThreatLevel, Vector3
from src.protocol.channel import InMemoryChannel


# ---------------------------------------------------------------------------
# Mock LLM that returns predetermined structured outputs
# ---------------------------------------------------------------------------


class MockStructuredLLM:
    """Mimics llm.with_structured_output(schema) — returns from a queue."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self._call_count = 0

    async def ainvoke(self, messages):
        if self._call_count < len(self._responses):
            result = self._responses[self._call_count]
            self._call_count += 1
            return result
        raise RuntimeError(f"MockStructuredLLM exhausted after {self._call_count} calls")


class MockLLM:
    """Mimics a BaseChatModel with with_structured_output support."""

    def __init__(self, responses_by_schema: dict[type, list]):
        self._by_schema = {k: list(v) for k, v in responses_by_schema.items()}
        self._indices = {k: 0 for k in responses_by_schema}

    def with_structured_output(self, schema):
        responses = self._by_schema.get(schema, [])
        idx = self._indices.get(schema, 0)
        # Return a mock that yields responses for this schema
        mock = MockStructuredLLM(responses[idx:])
        self._indices[schema] = idx + 1
        return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def collision_alert():
    return CollisionAlert(
        alert_id="ALERT-TEST",
        time_of_closest_approach=NOW,
        our_object=SpaceObject(
            object_id="SAT-A",
            object_name="Alpha",
            object_type="satellite",
            position=Vector3(x=6878.0, y=0.0, z=0.0),
            velocity=Vector3(x=0.0, y=7.5, z=0.0),
        ),
        threat_object=SpaceObject(
            object_id="SAT-B",
            object_name="Beta",
            object_type="satellite",
            position=Vector3(x=6878.5, y=0.1, z=0.0),
            velocity=Vector3(x=0.0, y=-7.5, z=0.0),
        ),
        miss_distance_m=150.0,
        probability_of_collision=0.003,
        threat_level=ThreatLevel.CRITICAL,
        relative_velocity=Vector3(x=0.0, y=-15.0, z=0.0),
        time_to_tca_seconds=21600.0,
    )


def _make_shared_data():
    return SharedCollisionData(
        alert_id="ALERT-TEST",
        time_of_closest_approach=NOW,
        miss_distance_m=150.0,
        probability_of_collision=0.003,
        threat_level="critical",
        our_object_id="SAT-A",
    )


def _make_maneuver():
    return ProposedManeuver(
        delta_v=Vector3(x=0.05, y=0.0, z=0.0),
        burn_start_time=NOW,
        burn_duration_seconds=15.0,
        expected_miss_distance_after_m=10000.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initiator_single_round_accepted(collision_alert):
    """Initiator proposes, responder accepts in round 1."""
    a_to_b = InMemoryChannel()
    b_to_a = InMemoryChannel()

    # Mock LLM responses for the initiator
    analysis = AnalysisOutput(
        severity_assessment="Critical conjunction, high Pc",
        who_should_maneuver="us",
        sharing_strategy="Share TCA, Pc, miss distance. Withhold covariance.",
        recommended_proposal_type=ProposalType.MANEUVER_OFFER,
    )
    proposal = ProposalOutput(
        shared_data=_make_shared_data(),
        proposal_type=ProposalType.MANEUVER_OFFER,
        proposed_maneuver=_make_maneuver(),
        reasoning="We will maneuver to increase miss distance",
    )
    decision = DecisionOutput(
        agreed=True,
        our_maneuver=_make_maneuver(),
        summary="Agreement reached: we maneuver, peer holds position",
    )

    mock_llm = MockLLM({
        AnalysisOutput: [analysis],
        ProposalOutput: [proposal],
        EvaluationOutput: [],  # Not needed — peer accepts
        DecisionOutput: [decision],
    })

    graph = build_initiator_graph(mock_llm, a_to_b, b_to_a)
    state = make_initiator_state(collision_alert, "SAT-A", "SAT-B", "sess-test")

    # Simulate responder accepting in a separate task
    async def fake_responder():
        # Wait for proposal from initiator
        incoming = await a_to_b.receive_message(timeout=10.0)
        # Send acceptance
        response = NegotiationMessage(
            message_id="resp-1",
            session_id="sess-test",
            round_number=1,
            phase=NegotiationPhase.RESPONSE,
            sender_satellite_id="SAT-B",
            receiver_satellite_id="SAT-A",
            timestamp=NOW,
            collision_data=incoming.collision_data,
            proposal_type=incoming.proposal_type,
            proposed_maneuver=incoming.proposed_maneuver,
            reasoning="Acceptable maneuver, we agree",
            accepted=True,
        )
        await b_to_a.send_message(response)

    responder_task = asyncio.create_task(fake_responder())
    result = await graph.ainvoke(state)
    await responder_task

    assert result["peer_accepted"] is True
    assert result["final_decision"] is not None
    assert result["current_round"] == 1


@pytest.mark.asyncio
async def test_responder_graph(collision_alert):
    """Responder evaluates proposal and sends response."""
    b_to_a = InMemoryChannel()

    eval_result = EvaluationOutput(
        accept=True,
        reasoning="Proposal adequately resolves the collision risk",
    )

    mock_llm = MockLLM({
        EvaluationOutput: [eval_result],
    })

    graph = build_responder_graph(mock_llm, b_to_a)

    # Create a proposal that the responder will evaluate
    proposal = NegotiationMessage(
        message_id="prop-1",
        session_id="sess-resp-test",
        round_number=1,
        phase=NegotiationPhase.PROPOSAL,
        sender_satellite_id="SAT-A",
        receiver_satellite_id="SAT-B",
        timestamp=NOW,
        collision_data=_make_shared_data(),
        proposal_type=ProposalType.MANEUVER_OFFER,
        proposed_maneuver=_make_maneuver(),
        reasoning="We offer to maneuver",
    )

    mirrored_alert = collision_alert.model_copy(
        update={
            "our_object": collision_alert.threat_object,
            "threat_object": collision_alert.our_object,
        }
    )

    state = make_responder_state(mirrored_alert, "SAT-B", "SAT-A", proposal)
    result = await graph.ainvoke(state)

    assert result["outbound_response"] is not None
    # Check the response was sent to the channel
    sent = await b_to_a.receive_message(timeout=5.0)
    assert sent.accepted is True
    assert sent.phase == NegotiationPhase.RESPONSE


@pytest.mark.asyncio
async def test_multi_round_rejected_then_accepted(collision_alert):
    """Round 1 rejected with counter, round 2 accepted."""
    a_to_b = InMemoryChannel()
    b_to_a = InMemoryChannel()

    analysis = AnalysisOutput(
        severity_assessment="Critical",
        who_should_maneuver="both",
        sharing_strategy="Share basic data",
        recommended_proposal_type=ProposalType.SHARED_MANEUVER,
    )

    # Round 1 and round 2 proposals
    proposal_r1 = ProposalOutput(
        shared_data=_make_shared_data(),
        proposal_type=ProposalType.SHARED_MANEUVER,
        proposed_maneuver=_make_maneuver(),
        reasoning="Round 1: both should maneuver",
    )
    proposal_r2 = ProposalOutput(
        shared_data=_make_shared_data(),
        proposal_type=ProposalType.MANEUVER_OFFER,
        proposed_maneuver=_make_maneuver(),
        reasoning="Round 2: compromise — we take full maneuver",
    )

    # Evaluate response in round 1 — peer rejected, we continue
    eval_r1 = EvaluationOutput(
        accept=False,
        reasoning="Peer's counter is not sufficient",
    )

    decision = DecisionOutput(
        agreed=True,
        our_maneuver=_make_maneuver(),
        summary="Agreed in round 2 after compromise",
    )

    mock_llm = MockLLM({
        AnalysisOutput: [analysis],
        ProposalOutput: [proposal_r1, proposal_r2],
        EvaluationOutput: [eval_r1],  # Only round 1 needs evaluation (round 2 peer accepts)
        DecisionOutput: [decision],
    })

    graph = build_initiator_graph(mock_llm, a_to_b, b_to_a)
    state = make_initiator_state(collision_alert, "SAT-A", "SAT-B", "sess-multi")

    async def fake_responder():
        # Round 1: reject with counter
        prop1 = await a_to_b.receive_message(timeout=10.0)
        response1 = NegotiationMessage(
            message_id="resp-r1",
            session_id="sess-multi",
            round_number=1,
            phase=NegotiationPhase.RESPONSE,
            sender_satellite_id="SAT-B",
            receiver_satellite_id="SAT-A",
            timestamp=NOW,
            collision_data=prop1.collision_data,
            proposal_type=prop1.proposal_type,
            proposed_maneuver=prop1.proposed_maneuver,
            reasoning="Reject: unfair fuel distribution",
            accepted=False,
            counter_proposal=_make_maneuver(),
        )
        await b_to_a.send_message(response1)

        # Round 2: accept
        prop2 = await a_to_b.receive_message(timeout=10.0)
        response2 = NegotiationMessage(
            message_id="resp-r2",
            session_id="sess-multi",
            round_number=2,
            phase=NegotiationPhase.RESPONSE,
            sender_satellite_id="SAT-B",
            receiver_satellite_id="SAT-A",
            timestamp=NOW,
            collision_data=prop2.collision_data,
            proposal_type=prop2.proposal_type,
            proposed_maneuver=prop2.proposed_maneuver,
            reasoning="Acceptable compromise",
            accepted=True,
        )
        await b_to_a.send_message(response2)

    responder_task = asyncio.create_task(fake_responder())
    result = await graph.ainvoke(state)
    await responder_task

    assert result["peer_accepted"] is True
    assert result["current_round"] == 2
    assert result["final_decision"] is not None
    assert len(result["messages_log"]) == 4  # 2 proposals + 2 responses
