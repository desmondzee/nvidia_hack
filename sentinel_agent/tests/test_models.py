"""Tests for Pydantic data models."""

import json
from datetime import datetime, timezone

import pytest

from src.models.maneuver import ManeuverDecision
from src.models.negotiation import (
    NegotiationMessage,
    NegotiationPhase,
    ProposalType,
    ProposedManeuver,
    SharedCollisionData,
)
from src.models.physics import CollisionAlert, SpaceObject, ThreatLevel, Vector3


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vector3():
    return Vector3(x=1.0, y=2.0, z=3.0)


@pytest.fixture
def space_object():
    return SpaceObject(
        object_id="SAT-001",
        object_name="TestSat",
        object_type="satellite",
        position=Vector3(x=6878.0, y=0.0, z=0.0),
        velocity=Vector3(x=0.0, y=7.5, z=0.0),
    )


@pytest.fixture
def collision_alert(space_object):
    return CollisionAlert(
        alert_id="ALERT-TEST",
        time_of_closest_approach=datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc),
        our_object=space_object,
        threat_object=SpaceObject(
            object_id="DEB-001",
            object_name="Debris-1",
            object_type="debris",
            position=Vector3(x=6878.5, y=0.1, z=0.0),
            velocity=Vector3(x=0.0, y=-7.5, z=0.0),
        ),
        miss_distance_m=200.0,
        probability_of_collision=0.005,
        threat_level=ThreatLevel.CRITICAL,
        relative_velocity=Vector3(x=0.0, y=-15.0, z=0.0),
        time_to_tca_seconds=3600.0,
    )


# ---------------------------------------------------------------------------
# Physics models
# ---------------------------------------------------------------------------


class TestVector3:
    def test_create(self, vector3):
        assert vector3.x == 1.0
        assert vector3.y == 2.0
        assert vector3.z == 3.0

    def test_json_roundtrip(self, vector3):
        data = json.loads(vector3.model_dump_json())
        restored = Vector3.model_validate(data)
        assert restored == vector3


class TestSpaceObject:
    def test_optional_covariance(self, space_object):
        assert space_object.covariance_diagonal is None

    def test_with_covariance(self):
        obj = SpaceObject(
            object_id="SAT-002",
            object_name="TestSat2",
            object_type="satellite",
            position=Vector3(x=7000.0, y=0.0, z=0.0),
            velocity=Vector3(x=0.0, y=7.4, z=0.0),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        )
        assert obj.covariance_diagonal is not None
        assert obj.covariance_diagonal.x == 0.05


class TestCollisionAlert:
    def test_json_roundtrip(self, collision_alert):
        data = json.loads(collision_alert.model_dump_json())
        restored = CollisionAlert.model_validate(data)
        assert restored.alert_id == collision_alert.alert_id
        assert restored.probability_of_collision == collision_alert.probability_of_collision

    def test_pc_bounds(self):
        """Probability of collision must be between 0 and 1."""
        with pytest.raises(Exception):
            CollisionAlert(
                alert_id="BAD",
                time_of_closest_approach=datetime.now(timezone.utc),
                our_object=SpaceObject(
                    object_id="A", object_name="A", object_type="satellite",
                    position=Vector3(x=0, y=0, z=0),
                    velocity=Vector3(x=0, y=0, z=0),
                ),
                threat_object=SpaceObject(
                    object_id="B", object_name="B", object_type="debris",
                    position=Vector3(x=0, y=0, z=0),
                    velocity=Vector3(x=0, y=0, z=0),
                ),
                miss_distance_m=100.0,
                probability_of_collision=1.5,  # Invalid: > 1.0
                threat_level=ThreatLevel.LOW,
                relative_velocity=Vector3(x=0, y=0, z=0),
                time_to_tca_seconds=100.0,
            )

    def test_json_schema_export(self):
        schema = CollisionAlert.model_json_schema()
        assert "properties" in schema
        assert "alert_id" in schema["properties"]

    def test_optional_weather(self, collision_alert):
        assert collision_alert.weather_parameters is None


# ---------------------------------------------------------------------------
# Negotiation models
# ---------------------------------------------------------------------------


class TestSharedCollisionData:
    def test_is_subset_of_alert(self, collision_alert):
        """SharedCollisionData should be constructable from a CollisionAlert."""
        shared = SharedCollisionData(
            alert_id=collision_alert.alert_id,
            time_of_closest_approach=collision_alert.time_of_closest_approach,
            miss_distance_m=collision_alert.miss_distance_m,
            probability_of_collision=collision_alert.probability_of_collision,
            threat_level=collision_alert.threat_level.value,
            our_object_id=collision_alert.our_object.object_id,
        )
        assert shared.alert_id == collision_alert.alert_id
        # Covariance data is NOT in SharedCollisionData (privacy)
        assert not hasattr(shared, "covariance_diagonal")


class TestNegotiationMessage:
    def test_proposal_message(self):
        msg = NegotiationMessage(
            message_id="msg-1",
            session_id="sess-1",
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
            reasoning="We should maneuver to avoid collision",
        )
        assert msg.phase == NegotiationPhase.PROPOSAL
        assert msg.accepted is None

    def test_round_number_bounds(self):
        """Round number must be 1-3."""
        with pytest.raises(Exception):
            NegotiationMessage(
                message_id="msg-bad",
                session_id="sess-1",
                round_number=4,  # Invalid
                phase=NegotiationPhase.PROPOSAL,
                sender_satellite_id="A",
                receiver_satellite_id="B",
                timestamp=datetime.now(timezone.utc),
                collision_data=SharedCollisionData(
                    alert_id="X", time_of_closest_approach=datetime.now(timezone.utc),
                    miss_distance_m=100.0, probability_of_collision=0.01,
                    threat_level="low", our_object_id="A",
                ),
                proposal_type=ProposalType.MANEUVER_REQUEST,
                reasoning="test",
            )

    def test_json_roundtrip(self):
        msg = NegotiationMessage(
            message_id="msg-rt",
            session_id="sess-rt",
            round_number=2,
            phase=NegotiationPhase.RESPONSE,
            sender_satellite_id="SAT-B",
            receiver_satellite_id="SAT-A",
            timestamp=datetime.now(timezone.utc),
            collision_data=SharedCollisionData(
                alert_id="ALERT-1",
                time_of_closest_approach=datetime.now(timezone.utc),
                miss_distance_m=200.0,
                probability_of_collision=0.005,
                threat_level="high",
                our_object_id="SAT-B",
            ),
            proposal_type=ProposalType.SHARED_MANEUVER,
            reasoning="Counter-proposal: both should maneuver",
            accepted=False,
            counter_proposal=ProposedManeuver(
                delta_v=Vector3(x=0.01, y=0.0, z=0.0),
                burn_start_time=datetime.now(timezone.utc),
                burn_duration_seconds=30.0,
                expected_miss_distance_after_m=5000.0,
            ),
        )
        data = json.loads(msg.model_dump_json())
        restored = NegotiationMessage.model_validate(data)
        assert restored.message_id == msg.message_id
        assert restored.counter_proposal is not None
        assert restored.accepted is False


# ---------------------------------------------------------------------------
# Maneuver decision
# ---------------------------------------------------------------------------


class TestManeuverDecision:
    def test_create(self):
        decision = ManeuverDecision(
            session_id="sess-1",
            alert_id="ALERT-1",
            our_satellite_id="SAT-A",
            peer_satellite_id="SAT-B",
            agreed=True,
            our_maneuver=ProposedManeuver(
                delta_v=Vector3(x=0.05, y=0.0, z=0.0),
                burn_start_time=datetime.now(timezone.utc),
                burn_duration_seconds=15.0,
                expected_miss_distance_after_m=10000.0,
            ),
            negotiation_summary="Agreement reached in round 1",
            rounds_taken=1,
            decided_at=datetime.now(timezone.utc),
        )
        assert decision.agreed is True
        assert decision.rounds_taken == 1
