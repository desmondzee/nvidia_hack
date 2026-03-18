"""Tests for the communication channel."""

import asyncio
from datetime import datetime, timezone

import pytest

from src.models.negotiation import (
    NegotiationMessage,
    NegotiationPhase,
    ProposalType,
    SharedCollisionData,
)
from src.protocol.channel import InMemoryChannel


def _make_message(msg_id: str = "msg-1", session_id: str = "sess-1") -> NegotiationMessage:
    return NegotiationMessage(
        message_id=msg_id,
        session_id=session_id,
        round_number=1,
        phase=NegotiationPhase.PROPOSAL,
        sender_satellite_id="SAT-A",
        receiver_satellite_id="SAT-B",
        timestamp=datetime.now(timezone.utc),
        collision_data=SharedCollisionData(
            alert_id="ALERT-1",
            time_of_closest_approach=datetime.now(timezone.utc),
            miss_distance_m=200.0,
            probability_of_collision=0.005,
            threat_level="critical",
            our_object_id="SAT-A",
        ),
        proposal_type=ProposalType.MANEUVER_OFFER,
        reasoning="Test proposal",
    )


@pytest.mark.asyncio
async def test_send_and_receive():
    channel = InMemoryChannel()
    msg = _make_message()
    await channel.send_message(msg)
    received = await channel.receive_message(timeout=5.0)
    assert received.message_id == msg.message_id


@pytest.mark.asyncio
async def test_fifo_ordering():
    channel = InMemoryChannel()
    msg1 = _make_message(msg_id="first")
    msg2 = _make_message(msg_id="second")
    await channel.send_message(msg1)
    await channel.send_message(msg2)
    r1 = await channel.receive_message(timeout=5.0)
    r2 = await channel.receive_message(timeout=5.0)
    assert r1.message_id == "first"
    assert r2.message_id == "second"


@pytest.mark.asyncio
async def test_receive_timeout():
    channel = InMemoryChannel()
    with pytest.raises(asyncio.TimeoutError):
        await channel.receive_message(timeout=0.1)


@pytest.mark.asyncio
async def test_bidirectional_channels():
    """Two channels simulate bidirectional communication."""
    a_to_b = InMemoryChannel()
    b_to_a = InMemoryChannel()

    proposal = _make_message(msg_id="proposal-1")
    await a_to_b.send_message(proposal)
    received_by_b = await a_to_b.receive_message(timeout=5.0)
    assert received_by_b.message_id == "proposal-1"

    response = _make_message(msg_id="response-1")
    await b_to_a.send_message(response)
    received_by_a = await b_to_a.receive_message(timeout=5.0)
    assert received_by_a.message_id == "response-1"


@pytest.mark.asyncio
async def test_concurrent_send_receive():
    """Producer and consumer running concurrently."""
    channel = InMemoryChannel()

    async def producer():
        await asyncio.sleep(0.05)
        await channel.send_message(_make_message(msg_id="delayed"))

    async def consumer():
        return await channel.receive_message(timeout=5.0)

    _, received = await asyncio.gather(producer(), consumer())
    assert received.message_id == "delayed"
