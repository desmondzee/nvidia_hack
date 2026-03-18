"""LangGraph-based negotiation agent for satellite collision avoidance.

Two graph variants:
  - Initiator graph: our physics agent detected the collision, we propose first
  - Responder graph: peer contacted us, we evaluate and respond

The initiator drives a multi-round loop (up to 3 rounds). The responder is
invoked once per round by the simulation runner.
"""

from __future__ import annotations

import asyncio
import operator
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from src.models.maneuver import ManeuverDecision
from src.models.negotiation import (
    NegotiationMessage,
    NegotiationPhase,
    ProposalType,
    ProposedManeuver,
    SharedCollisionData,
)
from src.models.physics import CollisionAlert, Vector3
from src.protocol.channel import NegotiationChannel


# ---------------------------------------------------------------------------
# Structured output schemas for LLM calls
# ---------------------------------------------------------------------------


class AnalysisOutput(BaseModel):
    """LLM output from analyzing a collision alert."""

    severity_assessment: str = Field(
        description="Assessment of collision severity based on Pc, miss distance, time to TCA"
    )
    who_should_maneuver: str = Field(
        description="'us', 'them', or 'both' — who should perform the avoidance maneuver"
    )
    sharing_strategy: str = Field(
        description="What data to share and what to withhold, with reasoning"
    )
    recommended_proposal_type: ProposalType


class ProposalOutput(BaseModel):
    """LLM output for generating a negotiation proposal."""

    shared_data: SharedCollisionData
    proposal_type: ProposalType
    proposed_maneuver: ProposedManeuver | None = None
    reasoning: str


class EvaluationOutput(BaseModel):
    """LLM output for evaluating a peer's proposal or response."""

    accept: bool = Field(description="Whether to accept the proposal/response")
    reasoning: str = Field(description="Explanation of the decision")
    counter_maneuver: ProposedManeuver | None = Field(
        default=None,
        description="If rejecting, propose an alternative maneuver",
    )


class DecisionOutput(BaseModel):
    """LLM output for making the final maneuver decision."""

    agreed: bool = Field(description="Whether both parties reached agreement")
    our_maneuver: ProposedManeuver | None = None
    peer_maneuver: ProposedManeuver | None = None
    summary: str = Field(description="Summary of the negotiation outcome")


# ---------------------------------------------------------------------------
# Graph state definitions
# ---------------------------------------------------------------------------


class InitiatorState(TypedDict):
    """State for the initiator negotiation graph."""

    # Inputs
    collision_alert: CollisionAlert
    our_satellite_id: str
    peer_satellite_id: str
    session_id: str

    # Round tracking
    current_round: int
    max_rounds: int

    # Negotiation messages (append-only log)
    messages_log: Annotated[list[NegotiationMessage], operator.add]

    # Current round's messages
    outbound_proposal: NegotiationMessage | None
    inbound_response: NegotiationMessage | None

    # Evaluation result
    peer_accepted: bool | None

    # Final output
    final_decision: ManeuverDecision | None

    # LLM reasoning
    analysis_notes: str
    sharing_strategy: str

    # RAG: historical context from the memory service (injected before graph runs)
    historical_context: str


class ResponderState(TypedDict):
    """State for the responder negotiation graph."""

    # Inputs
    collision_alert: CollisionAlert
    our_satellite_id: str
    peer_satellite_id: str
    session_id: str
    current_round: int
    max_rounds: int

    # Inbound proposal from peer
    inbound_proposal: NegotiationMessage

    # Internal
    evaluation_result: EvaluationOutput | None

    # Output
    outbound_response: NegotiationMessage | None
    messages_log: Annotated[list[NegotiationMessage], operator.add]

    # RAG: historical context from the memory service
    historical_context: str


# ---------------------------------------------------------------------------
# State factory helpers
# ---------------------------------------------------------------------------


def make_initiator_state(
    alert: CollisionAlert,
    our_id: str,
    peer_id: str,
    session_id: str | None = None,
    historical_context: str = "",
) -> dict:
    """Build initial state dict for the initiator graph."""
    return {
        "collision_alert": alert,
        "our_satellite_id": our_id,
        "peer_satellite_id": peer_id,
        "session_id": session_id or str(uuid.uuid4()),
        "current_round": 1,
        "max_rounds": 3,
        "messages_log": [],
        "outbound_proposal": None,
        "inbound_response": None,
        "peer_accepted": None,
        "final_decision": None,
        "analysis_notes": "",
        "sharing_strategy": "",
        "historical_context": historical_context,
    }


def make_responder_state(
    alert: CollisionAlert,
    our_id: str,
    peer_id: str,
    inbound_proposal: NegotiationMessage,
    historical_context: str = "",
) -> dict:
    """Build initial state dict for the responder graph."""
    return {
        "collision_alert": alert,
        "our_satellite_id": our_id,
        "peer_satellite_id": peer_id,
        "session_id": inbound_proposal.session_id,
        "current_round": inbound_proposal.round_number,
        "max_rounds": 3,
        "inbound_proposal": inbound_proposal,
        "evaluation_result": None,
        "outbound_response": None,
        "messages_log": [],
        "historical_context": historical_context,
    }


# ---------------------------------------------------------------------------
# Initiator node implementations
# ---------------------------------------------------------------------------

ANALYZE_SYSTEM_PROMPT = """\
You are a satellite collision avoidance specialist. Analyze the conjunction \
data and determine:
1. Severity assessment (consider Pc, miss distance, time to TCA)
2. Who should maneuver: 'us', 'them', or 'both'
3. What data is safe to share with the peer satellite — withhold exact \
covariance, internal capability data, and fuel reserves
4. Recommended proposal type (maneuver_request, maneuver_offer, or shared_maneuver)

If the threat object is debris, only 'us' can maneuver.\
"""

PROPOSAL_SYSTEM_PROMPT = """\
Generate a negotiation proposal for the peer satellite. Decide:
a) What collision data to share (filter sensitive info per the sharing strategy)
b) What maneuver to propose — specify delta-v vector, burn start time, \
burn duration, and expected miss distance after the maneuver
c) Whether to request they maneuver (maneuver_request), offer to maneuver \
yourself (maneuver_offer), or suggest both satellites adjust (shared_maneuver)

If this is a counter-proposal (round > 1), consider the peer's previous \
response and try to find a compromise. Use realistic delta-v values \
(typically 0.01–1.0 m/s for collision avoidance).\
"""

EVALUATE_RESPONSE_SYSTEM_PROMPT = """\
The peer satellite rejected our proposal and may have counter-proposed. \
Evaluate whether their counter-proposal adequately resolves the collision \
risk and is fair in terms of fuel cost distribution.

Decide: accept their counter-proposal, or prepare for another negotiation round.\
"""

DECISION_SYSTEM_PROMPT = """\
Based on the full negotiation history, produce the final maneuver decision. \
Specify what maneuver (if any) our satellite should execute and what we \
expect the peer to do.

If no agreement was reached after all rounds, choose the safest unilateral \
maneuver to avoid collision. Safety takes priority over fuel efficiency.\
"""

EVALUATE_PROPOSAL_SYSTEM_PROMPT = """\
A peer satellite has sent a collision avoidance proposal. Evaluate it \
against our own collision data:
1. Does their proposed maneuver adequately resolve the collision risk?
2. Is the fuel cost distribution fair?
3. Is there a better alternative?

Decide whether to accept, or reject with a counter-proposal. If rejecting, \
you MUST provide a counter_maneuver with realistic values.\
"""


def _emit_llm_output(
    queue: asyncio.Queue[dict[str, Any]] | None,
    pair_label: str | None,
    stage: str,
    output: dict[str, Any],
) -> None:
    """Emit LLM output to stream queue if configured."""
    if queue is None:
        return
    event = {
        "type": "llm_output",
        "pair_label": pair_label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"stage": stage, "output": output},
    }
    queue.put_nowait(event)


def _make_analyze_node(
    llm: BaseChatModel,
    stream_queue: asyncio.Queue[dict[str, Any]] | None = None,
    pair_label: str | None = None,
):
    """Node: analyze collision alert, decide sharing strategy."""

    async def analyze_collision(state: dict) -> dict:
        alert = CollisionAlert.model_validate(state["collision_alert"])
        structured_llm = llm.with_structured_output(AnalysisOutput)

        human_content = f"COLLISION ALERT:\n{alert.model_dump_json(indent=2)}"
        historical_context = state.get("historical_context", "")
        if historical_context:
            human_content = f"{historical_context}\n\n{human_content}"

        result: AnalysisOutput | None = await structured_llm.ainvoke([
            SystemMessage(content=ANALYZE_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ])

        if result is None:
            return {
                "analysis_notes": f"Moderate severity (Pc={alert.probability_of_collision}, miss={alert.miss_distance_m}m)",
                "sharing_strategy": "Share basic miss distance and Pc; withhold covariance and fuel data",
            }

        _emit_llm_output(
            stream_queue, pair_label, "analyze", result.model_dump(mode="json")
        )
        return {
            "analysis_notes": result.severity_assessment,
            "sharing_strategy": result.sharing_strategy,
        }

    return analyze_collision


def _make_generate_proposal_node(
    llm: BaseChatModel,
    send_channel: NegotiationChannel,
    stream_queue: asyncio.Queue[dict[str, Any]] | None = None,
    pair_label: str | None = None,
):
    """Node: generate and send a negotiation proposal."""

    async def generate_proposal(state: dict) -> dict:
        alert = CollisionAlert.model_validate(state["collision_alert"])
        structured_llm = llm.with_structured_output(ProposalOutput)
        current_round: int = state["current_round"]

        context_parts = [
            f"ANALYSIS: {state['analysis_notes']}",
            f"SHARING STRATEGY: {state['sharing_strategy']}",
            f"COLLISION ALERT:\n{alert.model_dump_json(indent=2)}",
            f"ROUND: {current_round} of {state['max_rounds']}",
        ]

        # Include previous response context for counter-proposals (round > 1)
        inbound = state.get("inbound_response")
        if inbound is not None:
            prev = NegotiationMessage.model_validate(inbound) if isinstance(inbound, dict) else inbound
            counter_json = prev.counter_proposal.model_dump_json(indent=2) if prev.counter_proposal else "None"
            context_parts.append(
                f"PEER'S PREVIOUS RESPONSE (they rejected):\n"
                f"Reasoning: {prev.reasoning}\n"
                f"Counter-proposal: {counter_json}"
            )

        result: ProposalOutput | None = await structured_llm.ainvoke([
            SystemMessage(content=PROPOSAL_SYSTEM_PROMPT),
            HumanMessage(content="\n\n".join(context_parts)),
        ])

        if result is None:
            result = ProposalOutput(
                shared_data=SharedCollisionData(
                    alert_id=alert.alert_id,
                    time_of_closest_approach=alert.time_of_closest_approach,
                    miss_distance_m=alert.miss_distance_m,
                    probability_of_collision=alert.probability_of_collision,
                    threat_level=alert.threat_level.value,
                    our_object_id=alert.our_object.object_id,
                ),
                proposal_type=ProposalType.MANEUVER_OFFER,
                proposed_maneuver=ProposedManeuver(
                    delta_v=Vector3(x=0.0, y=0.05, z=0.0),
                    burn_start_time=alert.time_of_closest_approach,
                    burn_duration_seconds=60.0,
                    expected_miss_distance_after_m=500.0,
                ),
                reasoning="Fallback: LLM structured output unavailable; proposing minimal maneuver.",
            )

        _emit_llm_output(
            stream_queue, pair_label, "proposal", result.model_dump(mode="json")
        )
        msg = NegotiationMessage(
            message_id=str(uuid.uuid4()),
            session_id=state["session_id"],
            round_number=current_round,
            phase=NegotiationPhase.PROPOSAL,
            sender_satellite_id=state["our_satellite_id"],
            receiver_satellite_id=state["peer_satellite_id"],
            timestamp=datetime.now(timezone.utc),
            collision_data=result.shared_data,
            proposal_type=result.proposal_type,
            proposed_maneuver=result.proposed_maneuver,
            reasoning=result.reasoning,
        )

        await send_channel.send_message(msg)

        return {
            "outbound_proposal": msg,
            "messages_log": [msg],
        }

    return generate_proposal


def _make_await_response_node(receive_channel: NegotiationChannel):
    """Node: wait for the peer's response via the channel."""

    async def await_response(state: dict) -> dict:
        response = await receive_channel.receive_message(timeout=120.0)
        return {
            "inbound_response": response,
            "messages_log": [response],
            "peer_accepted": response.accepted,
        }

    return await_response


def _make_evaluate_response_node(
    llm: BaseChatModel,
    stream_queue: asyncio.Queue[dict[str, Any]] | None = None,
    pair_label: str | None = None,
):
    """Node: evaluate the peer's response (only called when peer rejected)."""

    async def evaluate_response(state: dict) -> dict:
        inbound = state["inbound_response"]
        response = NegotiationMessage.model_validate(inbound) if isinstance(inbound, dict) else inbound

        # If peer accepted, skip LLM evaluation
        if response.accepted:
            return {"peer_accepted": True}

        alert = CollisionAlert.model_validate(state["collision_alert"])
        outbound = state["outbound_proposal"]
        proposal = NegotiationMessage.model_validate(outbound) if isinstance(outbound, dict) else outbound

        structured_llm = llm.with_structured_output(EvaluationOutput)

        result: EvaluationOutput | None = await structured_llm.ainvoke([
            SystemMessage(content=EVALUATE_RESPONSE_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"OUR COLLISION DATA:\n{alert.model_dump_json(indent=2)}\n\n"
                    f"OUR PROPOSAL:\n{proposal.model_dump_json(indent=2)}\n\n"
                    f"PEER RESPONSE:\n{response.model_dump_json(indent=2)}\n\n"
                    f"ROUND: {state['current_round']} of {state['max_rounds']}"
                )
            ),
        ])

        if result:
            _emit_llm_output(
                stream_queue, pair_label, "evaluate_response", result.model_dump(mode="json")
            )
        return {"peer_accepted": result.accept if result else True}

    return evaluate_response


def _make_increment_round_node():
    """Node: increment the round counter before looping back."""

    async def increment_round(state: dict) -> dict:
        return {"current_round": state["current_round"] + 1}

    return increment_round


def _make_decision_node(
    llm: BaseChatModel,
    stream_queue: asyncio.Queue[dict[str, Any]] | None = None,
    pair_label: str | None = None,
):
    """Node: produce the final ManeuverDecision."""

    async def make_decision(state: dict) -> dict:
        alert = CollisionAlert.model_validate(state["collision_alert"])
        structured_llm = llm.with_structured_output(DecisionOutput)

        log_entries = []
        for m in state.get("messages_log", []):
            msg = NegotiationMessage.model_validate(m) if isinstance(m, dict) else m
            log_entries.append(
                f"[Round {msg.round_number} {msg.phase.value}] "
                f"{msg.sender_satellite_id}: {msg.reasoning}"
            )
        log_summary = "\n".join(log_entries)

        result: DecisionOutput | None = await structured_llm.ainvoke([
            SystemMessage(content=DECISION_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"COLLISION ALERT:\n{alert.model_dump_json(indent=2)}\n\n"
                    f"NEGOTIATION LOG:\n{log_summary}\n\n"
                    f"PEER ACCEPTED: {state.get('peer_accepted', False)}\n"
                    f"ROUNDS TAKEN: {state['current_round']}"
                )
            ),
        ])

        if result is None:
            result = DecisionOutput(
                agreed=state.get("peer_accepted", False),
                our_maneuver=None,
                peer_maneuver=None,
                summary="Fallback: LLM structured output unavailable.",
            )

        _emit_llm_output(
            stream_queue, pair_label, "decision", result.model_dump(mode="json")
        )
        decision = ManeuverDecision(
            session_id=state["session_id"],
            alert_id=alert.alert_id,
            our_satellite_id=state["our_satellite_id"],
            peer_satellite_id=state["peer_satellite_id"],
            agreed=result.agreed,
            our_maneuver=result.our_maneuver,
            peer_maneuver=result.peer_maneuver,
            negotiation_summary=result.summary,
            rounds_taken=state["current_round"],
            decided_at=datetime.now(timezone.utc),
        )

        return {"final_decision": decision}

    return make_decision


# ---------------------------------------------------------------------------
# Conditional edge routing
# ---------------------------------------------------------------------------


def _should_continue_or_decide(state: dict) -> Literal["increment_round", "make_decision"]:
    """After evaluate_response: loop back (via increment) or finalize."""
    if state.get("peer_accepted"):
        return "make_decision"
    if state["current_round"] >= state["max_rounds"]:
        return "make_decision"
    return "increment_round"


# ---------------------------------------------------------------------------
# Build initiator graph
# ---------------------------------------------------------------------------


def build_initiator_graph(
    llm: BaseChatModel,
    send_channel: NegotiationChannel,
    receive_channel: NegotiationChannel,
    stream_queue: asyncio.Queue[dict[str, Any]] | None = None,
    pair_label: str | None = None,
) -> Any:
    """Build the LangGraph for the initiator role.

    Graph topology:
        START → analyze_collision → generate_proposal → await_response
                                          ↑                    ↓
                                   increment_round      evaluate_response
                                          ↑              ↓            ↓
                                          └─(rejected)───┘    (accepted/max)
                                                                     ↓
                                                              make_decision → END
    """
    graph = StateGraph(InitiatorState)

    graph.add_node(
        "analyze_collision",
        _make_analyze_node(llm, stream_queue=stream_queue, pair_label=pair_label),
    )
    graph.add_node(
        "generate_proposal",
        _make_generate_proposal_node(
            llm, send_channel,
            stream_queue=stream_queue, pair_label=pair_label,
        ),
    )
    graph.add_node("await_response", _make_await_response_node(receive_channel))
    graph.add_node(
        "evaluate_response",
        _make_evaluate_response_node(llm, stream_queue=stream_queue, pair_label=pair_label),
    )
    graph.add_node("increment_round", _make_increment_round_node())
    graph.add_node(
        "make_decision",
        _make_decision_node(llm, stream_queue=stream_queue, pair_label=pair_label),
    )

    graph.add_edge(START, "analyze_collision")
    graph.add_edge("analyze_collision", "generate_proposal")
    graph.add_edge("generate_proposal", "await_response")
    graph.add_edge("await_response", "evaluate_response")
    graph.add_conditional_edges(
        "evaluate_response",
        _should_continue_or_decide,
        {
            "increment_round": "increment_round",
            "make_decision": "make_decision",
        },
    )
    graph.add_edge("increment_round", "generate_proposal")
    graph.add_edge("make_decision", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Responder node implementations
# ---------------------------------------------------------------------------


def _make_receive_proposal_node():
    """Node: pass through — inbound proposal is already in state."""

    async def receive_proposal(state: dict) -> dict:
        return {}

    return receive_proposal


def _make_evaluate_proposal_node(
    llm: BaseChatModel,
    stream_queue: asyncio.Queue[dict[str, Any]] | None = None,
    pair_label: str | None = None,
):
    """Node: evaluate the peer's proposal against our collision data."""

    async def evaluate_proposal(state: dict) -> dict:
        inbound = state["inbound_proposal"]
        proposal = NegotiationMessage.model_validate(inbound) if isinstance(inbound, dict) else inbound
        alert = CollisionAlert.model_validate(state["collision_alert"])

        structured_llm = llm.with_structured_output(EvaluationOutput)

        human_parts = [
            f"OUR COLLISION DATA:\n{alert.model_dump_json(indent=2)}",
            f"PEER PROPOSAL:\n{proposal.model_dump_json(indent=2)}",
            f"ROUND: {state['current_round']} of {state['max_rounds']}",
        ]
        historical_context = state.get("historical_context", "")
        if historical_context:
            human_parts.insert(0, historical_context)

        result: EvaluationOutput | None = await structured_llm.ainvoke([
            SystemMessage(content=EVALUATE_PROPOSAL_SYSTEM_PROMPT),
            HumanMessage(content="\n\n".join(human_parts)),
        ])

        if result is None:
            result = EvaluationOutput(
                accept=True,
                reasoning="Fallback: LLM structured output unavailable; accepting proposal.",
                counter_maneuver=None,
            )

        _emit_llm_output(
            stream_queue, pair_label, "evaluate_proposal", result.model_dump(mode="json")
        )
        return {"evaluation_result": result}

    return evaluate_proposal


def _make_generate_response_node(llm: BaseChatModel, send_channel: NegotiationChannel):
    """Node: build and send a RESPONSE message based on evaluation."""

    async def generate_response(state: dict) -> dict:
        inbound = state["inbound_proposal"]
        proposal = NegotiationMessage.model_validate(inbound) if isinstance(inbound, dict) else inbound
        eval_result = state["evaluation_result"]
        evaluation = EvaluationOutput.model_validate(eval_result) if isinstance(eval_result, dict) else eval_result

        msg = NegotiationMessage(
            message_id=str(uuid.uuid4()),
            session_id=state["session_id"],
            round_number=state["current_round"],
            phase=NegotiationPhase.RESPONSE,
            sender_satellite_id=state["our_satellite_id"],
            receiver_satellite_id=state["peer_satellite_id"],
            timestamp=datetime.now(timezone.utc),
            collision_data=proposal.collision_data,
            proposal_type=proposal.proposal_type,
            proposed_maneuver=proposal.proposed_maneuver,
            reasoning=evaluation.reasoning,
            accepted=evaluation.accept,
            counter_proposal=evaluation.counter_maneuver,
        )

        await send_channel.send_message(msg)

        return {
            "outbound_response": msg,
            "messages_log": [msg],
        }

    return generate_response


# ---------------------------------------------------------------------------
# Build responder graph
# ---------------------------------------------------------------------------


def build_responder_graph(
    llm: BaseChatModel,
    send_channel: NegotiationChannel,
    stream_queue: asyncio.Queue[dict[str, Any]] | None = None,
    pair_label: str | None = None,
) -> Any:
    """Build the LangGraph for the responder role.

    Graph topology:
        START → receive_proposal → evaluate_proposal → generate_response → END

    Invoked once per round — the simulation runner coordinates multi-round.
    """
    graph = StateGraph(ResponderState)

    graph.add_node("receive_proposal", _make_receive_proposal_node())
    graph.add_node(
        "evaluate_proposal",
        _make_evaluate_proposal_node(llm, stream_queue=stream_queue, pair_label=pair_label),
    )
    graph.add_node("generate_response", _make_generate_response_node(llm, send_channel))

    graph.add_edge(START, "receive_proposal")
    graph.add_edge("receive_proposal", "evaluate_proposal")
    graph.add_edge("evaluate_proposal", "generate_response")
    graph.add_edge("generate_response", END)

    return graph.compile()
