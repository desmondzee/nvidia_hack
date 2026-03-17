"""End-to-end simulation: satellite collision avoidance negotiation.

Supports 2-satellite (head_on, debris, low_probability) and 3-satellite
(three_way) scenarios. Displays all negotiation communications between agents.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from src.agents.llm import get_llm
from src.agents.negotiation_agent import (
    build_initiator_graph,
    build_responder_graph,
    make_initiator_state,
    make_responder_state,
)
from src.models.maneuver import ManeuverDecision
from src.models.negotiation import NegotiationMessage
from src.models.physics import CollisionAlert
from src.physics_interface.mock import (
    get_mock_alert,
    make_three_way_alert_ac,
    make_three_way_alert_bc,
)
from src.protocol.channel import InMemoryChannel, MessageLog, StreamableChannel

logger = logging.getLogger(__name__)


def _emit_stream_event(
    stream_queue: asyncio.Queue[dict] | None,
    event_type: str,
    pair_label: str | None = None,
    data: dict | None = None,
) -> None:
    """Emit an event to the stream queue if configured."""
    if stream_queue is None:
        return
    event = {
        "type": event_type,
        "pair_label": pair_label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }
    stream_queue.put_nowait(event)


def _mirror_alert(alert: CollisionAlert) -> CollisionAlert:
    """Flip the alert to represent the peer's perspective."""
    return alert.model_copy(
        update={
            "our_object": alert.threat_object,
            "threat_object": alert.our_object,
        }
    )


def _format_message(msg: NegotiationMessage, pair_label: str) -> str:
    """Format a negotiation message for display."""
    phase = msg.phase.value.upper()
    direction = f"{msg.sender_satellite_id} → {msg.receiver_satellite_id}"
    lines = [
        f"  [{pair_label}] Round {msg.round_number} | {phase} | {direction}",
        f"    Reasoning: {msg.reasoning}",
    ]
    if msg.proposed_maneuver:
        m = msg.proposed_maneuver
        lines.append(
            f"    Proposed: Δv=({m.delta_v.x:.4f},{m.delta_v.y:.4f},{m.delta_v.z:.4f}) m/s, "
            f"miss={m.expected_miss_distance_after_m:.1f}m"
        )
    if msg.accepted is not None:
        lines.append(f"    Accepted: {msg.accepted}")
    if msg.counter_proposal:
        c = msg.counter_proposal
        lines.append(
            f"    Counter: Δv=({c.delta_v.x:.4f},{c.delta_v.y:.4f},{c.delta_v.z:.4f}) m/s"
        )
    return "\n".join(lines)


def _print_communications(message_logs: dict[str, list[MessageLog]]) -> None:
    """Print all negotiation communications, sorted by timestamp."""
    all_msgs: list[tuple[datetime, str, NegotiationMessage]] = []
    for pair_label, logs in message_logs.items():
        for log in logs:
            for msg in log.messages:
                m = NegotiationMessage.model_validate(msg) if isinstance(msg, dict) else msg
                all_msgs.append((m.timestamp, pair_label, m))

    all_msgs.sort(key=lambda x: (x[2].round_number, x[0]))

    print(f"\n{'='*70}")
    print("NEGOTIATION COMMUNICATIONS")
    print(f"{'='*70}")
    for _, pair_label, msg in all_msgs:
        print(_format_message(msg, pair_label))
        print()
    print(f"{'='*70}\n")


async def _run_responder_loop(
    responder_graph,
    alert: CollisionAlert,
    our_id: str,
    peer_id: str,
    receive_channel: InMemoryChannel,
    send_channel: InMemoryChannel,
    max_rounds: int = 3,
) -> None:
    """Responder loop: listen for proposals and respond, one round at a time."""
    for _ in range(1, max_rounds + 1):
        try:
            proposal: NegotiationMessage = await receive_channel.receive_message(
                timeout=120.0
            )
        except asyncio.TimeoutError:
            logger.info("Responder: no more proposals received, exiting loop")
            break

        logger.info(
            f"Responder {our_id}: received round {proposal.round_number} proposal from {proposal.sender_satellite_id}"
        )

        state = make_responder_state(
            alert=alert,
            our_id=our_id,
            peer_id=peer_id,
            inbound_proposal=proposal,
        )

        result = await responder_graph.ainvoke(state)

        response = result.get("outbound_response")
        if response:
            logger.info(
                f"Responder {our_id}: sent round {response.round_number} response "
                f"(accepted={response.accepted})"
            )

        if response and response.accepted:
            break


async def _run_two_satellite_simulation(
    scenario: str,
    llm,
    message_logs: dict[str, list[MessageLog]],
    stream_queue: asyncio.Queue[dict] | None = None,
) -> tuple[ManeuverDecision | None, dict]:
    """Run 2-satellite negotiation (A-B)."""
    pair_label = "A↔B"
    _emit_stream_event(stream_queue, "simulation_start", pair_label, {"scenario": scenario})

    alert_a = get_mock_alert(scenario)
    alert_b = _mirror_alert(alert_a)

    sat_a_id = alert_a.our_object.object_id
    sat_b_id = alert_a.threat_object.object_id

    log_ab = MessageLog()
    message_logs[pair_label] = [log_ab]

    if stream_queue:
        a_to_b = StreamableChannel(message_log=log_ab, stream_queue=stream_queue, pair_label=pair_label)
        b_to_a = StreamableChannel(message_log=log_ab, stream_queue=stream_queue, pair_label=pair_label)
    else:
        a_to_b = InMemoryChannel(message_log=log_ab)
        b_to_a = InMemoryChannel(message_log=log_ab)

    initiator_graph = build_initiator_graph(
        llm=llm,
        send_channel=a_to_b,
        receive_channel=b_to_a,
        stream_queue=stream_queue,
        pair_label=pair_label,
    )
    responder_graph = build_responder_graph(
        llm=llm,
        send_channel=b_to_a,
        stream_queue=stream_queue,
        pair_label=pair_label,
    )

    initiator_state = make_initiator_state(
        alert=alert_a,
        our_id=sat_a_id,
        peer_id=sat_b_id,
    )

    initiator_task = asyncio.create_task(initiator_graph.ainvoke(initiator_state))
    responder_task = asyncio.create_task(
        _run_responder_loop(
            responder_graph=responder_graph,
            alert=alert_b,
            our_id=sat_b_id,
            peer_id=sat_a_id,
            receive_channel=a_to_b,
            send_channel=b_to_a,
        )
    )

    initiator_result = await initiator_task
    responder_task.cancel()
    try:
        await responder_task
    except asyncio.CancelledError:
        pass

    decision = initiator_result.get("final_decision")
    if isinstance(decision, dict):
        decision = ManeuverDecision.model_validate(decision)

    if decision:
        _emit_stream_event(
            stream_queue, "decision", pair_label, decision.model_dump(mode="json")
        )
    _emit_stream_event(stream_queue, "simulation_end", pair_label)
    return decision, initiator_result


async def _run_three_satellite_simulation(
    llm,
    message_logs: dict[str, list[MessageLog]],
    stream_queue: asyncio.Queue[dict] | None = None,
) -> tuple[list[ManeuverDecision | None], dict]:
    """Run 3-satellite negotiation: A-B, A-C, B-C in parallel."""
    _emit_stream_event(stream_queue, "simulation_start", None, {"scenario": "three_way"})

    alert_ab = get_mock_alert("three_way")
    alert_ba = _mirror_alert(alert_ab)

    alert_ac = make_three_way_alert_ac()
    alert_ca = _mirror_alert(alert_ac)

    alert_bc = make_three_way_alert_bc()
    alert_cb = _mirror_alert(alert_bc)

    sat_a, sat_b, sat_c = "SAT-A-001", "SAT-B-001", "SAT-C-001"

    log_ab = MessageLog()
    log_ac = MessageLog()
    log_bc = MessageLog()
    message_logs["A↔B"] = [log_ab]
    message_logs["A↔C"] = [log_ac]
    message_logs["B↔C"] = [log_bc]

    if stream_queue:
        a_to_b = StreamableChannel(message_log=log_ab, stream_queue=stream_queue, pair_label="A↔B")
        b_to_a = StreamableChannel(message_log=log_ab, stream_queue=stream_queue, pair_label="A↔B")
        a_to_c = StreamableChannel(message_log=log_ac, stream_queue=stream_queue, pair_label="A↔C")
        c_to_a = StreamableChannel(message_log=log_ac, stream_queue=stream_queue, pair_label="A↔C")
        b_to_c = StreamableChannel(message_log=log_bc, stream_queue=stream_queue, pair_label="B↔C")
        c_to_b = StreamableChannel(message_log=log_bc, stream_queue=stream_queue, pair_label="B↔C")
    else:
        a_to_b = InMemoryChannel(message_log=log_ab)
        b_to_a = InMemoryChannel(message_log=log_ab)
        a_to_c = InMemoryChannel(message_log=log_ac)
        c_to_a = InMemoryChannel(message_log=log_ac)
        b_to_c = InMemoryChannel(message_log=log_bc)
        c_to_b = InMemoryChannel(message_log=log_bc)

    def build_pair(alert_init, alert_resp, init_id, resp_id, send_ch, recv_ch, pair_label):
        init_graph = build_initiator_graph(
            llm=llm,
            send_channel=send_ch,
            receive_channel=recv_ch,
            stream_queue=stream_queue,
            pair_label=pair_label,
        )
        resp_graph = build_responder_graph(
            llm=llm,
            send_channel=recv_ch,
            stream_queue=stream_queue,
            pair_label=pair_label,
        )
        init_state = make_initiator_state(alert=alert_init, our_id=init_id, peer_id=resp_id)
        return init_graph, resp_graph, init_state, alert_resp, resp_id, init_id, send_ch, recv_ch

    pair_ab = build_pair(alert_ab, alert_ba, sat_a, sat_b, a_to_b, b_to_a, "A↔B")
    pair_ac = build_pair(alert_ac, alert_ca, sat_a, sat_c, a_to_c, c_to_a, "A↔C")
    pair_bc = build_pair(alert_bc, alert_cb, sat_b, sat_c, b_to_c, c_to_b, "B↔C")

    async def run_pair(pair, pair_name):
        (init_graph, resp_graph, init_state, alert_resp, resp_id, init_id, send_ch, recv_ch) = pair
        init_task = asyncio.create_task(init_graph.ainvoke(init_state))
        resp_task = asyncio.create_task(
            _run_responder_loop(
                responder_graph=resp_graph,
                alert=alert_resp,
                our_id=resp_id,
                peer_id=init_id,
                receive_channel=send_ch,
                send_channel=recv_ch,
            )
        )
        result = await init_task
        resp_task.cancel()
        try:
            await resp_task
        except asyncio.CancelledError:
            pass
        return result

    results = await asyncio.gather(
        run_pair(pair_ab, "A-B"),
        run_pair(pair_ac, "A-C"),
        run_pair(pair_bc, "B-C"),
    )

    decisions = []
    for r, pair in zip(results, ["A↔B", "A↔C", "B↔C"]):
        d = r.get("final_decision")
        if isinstance(d, dict):
            d = ManeuverDecision.model_validate(d)
        decisions.append(d)
        if d:
            _emit_stream_event(stream_queue, "decision", pair, d.model_dump(mode="json"))

    _emit_stream_event(stream_queue, "simulation_end", None)
    return decisions, results[0]


def _print_result_two(decision: ManeuverDecision | None, scenario: str) -> None:
    """Print 2-satellite negotiation result."""
    if not decision:
        print("ERROR: No decision produced!")
        return

    print(f"\n{'='*60}")
    print(f"NEGOTIATION RESULT ({scenario})")
    print(f"{'='*60}")
    print(f"Agreement reached: {decision.agreed}")
    print(f"Rounds taken: {decision.rounds_taken}")
    print(f"Summary: {decision.negotiation_summary}")
    if decision.our_maneuver:
        m = decision.our_maneuver
        print(f"\nOur maneuver:")
        print(f"  Delta-V: ({m.delta_v.x:.4f}, {m.delta_v.y:.4f}, {m.delta_v.z:.4f}) m/s")
        print(f"  Expected miss distance after: {m.expected_miss_distance_after_m:.1f}m")
    if decision.peer_maneuver:
        m = decision.peer_maneuver
        print(f"\nPeer maneuver:")
        print(f"  Delta-V: ({m.delta_v.x:.4f}, {m.delta_v.y:.4f}, {m.delta_v.z:.4f}) m/s")
        print(f"  Expected miss distance after: {m.expected_miss_distance_after_m:.1f}m")
    print(f"{'='*60}\n")


def _print_result_three(decisions: list[ManeuverDecision | None]) -> None:
    """Print 3-satellite negotiation results."""
    pairs = ["A↔B", "A↔C", "B↔C"]
    print(f"\n{'='*60}")
    print("NEGOTIATION RESULTS (3 satellites)")
    print(f"{'='*60}")
    for pair, decision in zip(pairs, decisions):
        print(f"\n--- {pair} ---")
        if decision:
            print(f"Agreement: {decision.agreed} | Rounds: {decision.rounds_taken}")
            print(f"Summary: {decision.negotiation_summary}")
        else:
            print("No decision")
    print(f"\n{'='*60}\n")


async def run_simulation(
    scenario: str = "head_on",
    llm_provider: str = "nvidia",
    stream_queue: asyncio.Queue[dict] | None = None,
) -> tuple[ManeuverDecision | list[ManeuverDecision | None] | None, dict | list]:
    """Run satellite collision avoidance negotiation.

    Args:
        scenario: "head_on", "debris", "low_probability" (2 sats), or "three_way" (3 sats)
        llm_provider: "nvidia", "google", or "ollama"
        stream_queue: Optional queue to emit events for streaming (negotiation_message,
            llm_output, decision, simulation_start, simulation_end)

    Returns:
        For 2-sat: (ManeuverDecision, initiator_result)
        For 3-sat: (list of ManeuverDecisions, first_result)
    """
    message_logs: dict[str, list[MessageLog]] = {}
    llm = get_llm(llm_provider)

    if scenario == "three_way":
        logger.info("=== Simulation: three_way (3 satellites) ===")
        logger.info("Satellite A: SAT-A-001 (SatComm-Alpha)")
        logger.info("Satellite B: SAT-B-001 (SatComm-Beta)")
        logger.info("Satellite C: SAT-C-001 (WeatherSat-Gamma)")

        decisions, result = await _run_three_satellite_simulation(
            llm, message_logs, stream_queue=stream_queue
        )

        _print_communications(message_logs)
        _print_result_three(decisions)

        return decisions, result
    else:
        alert = get_mock_alert(scenario)
        logger.info(f"=== Simulation: {scenario} ===")
        logger.info(f"Satellite A: {alert.our_object.object_id} ({alert.our_object.object_name})")
        logger.info(f"Satellite B: {alert.threat_object.object_id} ({alert.threat_object.object_name})")
        logger.info(f"Miss distance: {alert.miss_distance_m}m, Pc: {alert.probability_of_collision}")

        decision, result = await _run_two_satellite_simulation(
            scenario, llm, message_logs, stream_queue=stream_queue
        )

        _print_communications(message_logs)
        _print_result_two(decision, scenario)

        return decision, result


async def main():
    """Run the default simulation."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    await run_simulation(scenario="three_way", llm_provider="ollama")


if __name__ == "__main__":
    asyncio.run(main())
