"""Mock collision alert generator for testing without the real physics agent."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.models.physics import CollisionAlert, SpaceObject, ThreatLevel, Vector3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_head_on_collision() -> CollisionAlert:
    """High-severity head-on collision between two active satellites."""
    tca = _now() + timedelta(hours=6)
    return CollisionAlert(
        alert_id="ALERT-001",
        time_of_closest_approach=tca,
        our_object=SpaceObject(
            object_id="SAT-A-001",
            object_name="SatComm-Alpha",
            object_type="satellite",
            position=Vector3(x=6878.0, y=0.0, z=0.0),
            velocity=Vector3(x=0.0, y=7.5, z=0.0),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        threat_object=SpaceObject(
            object_id="SAT-B-001",
            object_name="SatComm-Beta",
            object_type="satellite",
            position=Vector3(x=6878.5, y=0.1, z=0.0),
            velocity=Vector3(x=0.0, y=-7.5, z=0.0),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        miss_distance_m=150.0,
        probability_of_collision=0.0023,
        threat_level=ThreatLevel.CRITICAL,
        relative_velocity=Vector3(x=0.0, y=-15.0, z=0.0),
        time_to_tca_seconds=6 * 3600,
        weather_parameters={"solar_flux_f10_7": 150.0, "kp_index": 3},
    )


def make_debris_avoidance() -> CollisionAlert:
    """Medium-severity conjunction with debris (only our satellite can maneuver)."""
    tca = _now() + timedelta(hours=12)
    return CollisionAlert(
        alert_id="ALERT-002",
        time_of_closest_approach=tca,
        our_object=SpaceObject(
            object_id="SAT-A-001",
            object_name="SatComm-Alpha",
            object_type="satellite",
            position=Vector3(x=7000.0, y=100.0, z=50.0),
            velocity=Vector3(x=-1.0, y=7.4, z=0.5),
        ),
        threat_object=SpaceObject(
            object_id="DEB-42819",
            object_name="Cosmos-2251-Fragment-47",
            object_type="debris",
            position=Vector3(x=7000.2, y=100.5, z=50.1),
            velocity=Vector3(x=3.0, y=-5.0, z=1.0),
        ),
        miss_distance_m=320.0,
        probability_of_collision=0.00085,
        threat_level=ThreatLevel.HIGH,
        relative_velocity=Vector3(x=4.0, y=-12.4, z=0.5),
        time_to_tca_seconds=12 * 3600,
    )


def make_low_probability() -> CollisionAlert:
    """Low-probability conjunction — likely no maneuver needed."""
    tca = _now() + timedelta(hours=48)
    return CollisionAlert(
        alert_id="ALERT-003",
        time_of_closest_approach=tca,
        our_object=SpaceObject(
            object_id="SAT-A-001",
            object_name="SatComm-Alpha",
            object_type="satellite",
            position=Vector3(x=6900.0, y=200.0, z=0.0),
            velocity=Vector3(x=0.5, y=7.45, z=0.0),
        ),
        threat_object=SpaceObject(
            object_id="SAT-C-003",
            object_name="WeatherSat-Gamma",
            object_type="satellite",
            position=Vector3(x=6901.0, y=201.0, z=0.5),
            velocity=Vector3(x=0.4, y=7.44, z=0.01),
        ),
        miss_distance_m=2500.0,
        probability_of_collision=0.000012,
        threat_level=ThreatLevel.LOW,
        relative_velocity=Vector3(x=-0.1, y=-0.01, z=-0.01),
        time_to_tca_seconds=48 * 3600,
    )


def make_three_way_conjunction() -> CollisionAlert:
    """Three-satellite conjunction: A, B, C in close formation.

    Returns the A-B pair; use _mirror_* helpers for B-A, A-C, C-A, B-C, C-B.
    """
    tca = _now() + timedelta(hours=8)
    return CollisionAlert(
        alert_id="ALERT-004",
        time_of_closest_approach=tca,
        our_object=SpaceObject(
            object_id="SAT-A-001",
            object_name="SatComm-Alpha",
            object_type="satellite",
            position=Vector3(x=6880.0, y=0.0, z=0.0),
            velocity=Vector3(x=0.0, y=7.5, z=0.0),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        threat_object=SpaceObject(
            object_id="SAT-B-001",
            object_name="SatComm-Beta",
            object_type="satellite",
            position=Vector3(x=6880.3, y=0.05, z=0.02),
            velocity=Vector3(x=0.0, y=-7.5, z=0.0),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        miss_distance_m=180.0,
        probability_of_collision=0.0018,
        threat_level=ThreatLevel.HIGH,
        relative_velocity=Vector3(x=0.0, y=-15.0, z=0.0),
        time_to_tca_seconds=8 * 3600,
        weather_parameters={"solar_flux_f10_7": 145.0, "kp_index": 2},
    )


def make_three_way_alert_ac() -> CollisionAlert:
    """A-C pair for three-way scenario."""
    base = make_three_way_conjunction()
    return CollisionAlert(
        alert_id="ALERT-004-AC",
        time_of_closest_approach=base.time_of_closest_approach,
        our_object=base.our_object,
        threat_object=SpaceObject(
            object_id="SAT-C-001",
            object_name="WeatherSat-Gamma",
            object_type="satellite",
            position=Vector3(x=6880.1, y=0.02, z=0.05),
            velocity=Vector3(x=0.01, y=7.48, z=-0.01),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        miss_distance_m=220.0,
        probability_of_collision=0.0012,
        threat_level=ThreatLevel.HIGH,
        relative_velocity=Vector3(x=0.01, y=-0.02, z=-0.01),
        time_to_tca_seconds=8 * 3600,
    )


def make_three_way_alert_bc() -> CollisionAlert:
    """B-C pair for three-way scenario."""
    base = make_three_way_conjunction()
    return CollisionAlert(
        alert_id="ALERT-004-BC",
        time_of_closest_approach=base.time_of_closest_approach,
        our_object=base.threat_object,
        threat_object=SpaceObject(
            object_id="SAT-C-001",
            object_name="WeatherSat-Gamma",
            object_type="satellite",
            position=Vector3(x=6880.1, y=0.02, z=0.05),
            velocity=Vector3(x=0.01, y=7.48, z=-0.01),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        miss_distance_m=195.0,
        probability_of_collision=0.0015,
        threat_level=ThreatLevel.HIGH,
        relative_velocity=Vector3(x=0.01, y=7.52, z=-0.01),
        time_to_tca_seconds=8 * 3600,
    )


# --- Six-satellite scenario: 3 pairs (A-B, C-D, E-F), toggle 20s per pair ---

def make_six_satellite_alert_ab() -> CollisionAlert:
    """Pair 1: A↔B for six-satellite scenario."""
    tca = _now() + timedelta(hours=6)
    return CollisionAlert(
        alert_id="ALERT-006-AB",
        time_of_closest_approach=tca,
        our_object=SpaceObject(
            object_id="SAT-A-001",
            object_name="SatComm-Alpha",
            object_type="satellite",
            position=Vector3(x=6878.0, y=0.0, z=0.0),
            velocity=Vector3(x=0.0, y=7.5, z=0.0),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        threat_object=SpaceObject(
            object_id="SAT-B-001",
            object_name="SatComm-Beta",
            object_type="satellite",
            position=Vector3(x=6878.5, y=0.1, z=0.0),
            velocity=Vector3(x=0.0, y=-7.5, z=0.0),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        miss_distance_m=180.0,
        probability_of_collision=0.0018,
        threat_level=ThreatLevel.HIGH,
        relative_velocity=Vector3(x=0.0, y=-15.0, z=0.0),
        time_to_tca_seconds=6 * 3600,
        weather_parameters={"solar_flux_f10_7": 150.0, "kp_index": 3},
    )


def make_six_satellite_alert_cd() -> CollisionAlert:
    """Pair 2: C↔D for six-satellite scenario."""
    tca = _now() + timedelta(hours=8)
    return CollisionAlert(
        alert_id="ALERT-006-CD",
        time_of_closest_approach=tca,
        our_object=SpaceObject(
            object_id="SAT-C-001",
            object_name="WeatherSat-Gamma",
            object_type="satellite",
            position=Vector3(x=6880.0, y=100.0, z=50.0),
            velocity=Vector3(x=-0.5, y=7.4, z=0.3),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        threat_object=SpaceObject(
            object_id="SAT-D-001",
            object_name="ImagingSat-Delta",
            object_type="satellite",
            position=Vector3(x=6880.2, y=100.2, z=50.1),
            velocity=Vector3(x=-0.4, y=-7.5, z=0.2),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        miss_distance_m=220.0,
        probability_of_collision=0.0015,
        threat_level=ThreatLevel.HIGH,
        relative_velocity=Vector3(x=0.1, y=-14.9, z=-0.1),
        time_to_tca_seconds=8 * 3600,
        weather_parameters={"solar_flux_f10_7": 148.0, "kp_index": 2},
    )


def make_six_satellite_alert_ef() -> CollisionAlert:
    """Pair 3: E↔F for six-satellite scenario."""
    tca = _now() + timedelta(hours=10)
    return CollisionAlert(
        alert_id="ALERT-006-EF",
        time_of_closest_approach=tca,
        our_object=SpaceObject(
            object_id="SAT-E-001",
            object_name="NavSat-Epsilon",
            object_type="satellite",
            position=Vector3(x=6890.0, y=200.0, z=0.0),
            velocity=Vector3(x=0.3, y=7.45, z=0.0),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        threat_object=SpaceObject(
            object_id="SAT-F-001",
            object_name="CommsSat-Zeta",
            object_type="satellite",
            position=Vector3(x=6890.3, y=200.1, z=0.02),
            velocity=Vector3(x=-0.2, y=-7.48, z=0.01),
            covariance_diagonal=Vector3(x=0.05, y=0.05, z=0.02),
        ),
        miss_distance_m=195.0,
        probability_of_collision=0.0016,
        threat_level=ThreatLevel.HIGH,
        relative_velocity=Vector3(x=-0.5, y=-14.93, z=0.01),
        time_to_tca_seconds=10 * 3600,
        weather_parameters={"solar_flux_f10_7": 145.0, "kp_index": 2},
    )


def get_six_satellite_alert(pair: str) -> CollisionAlert:
    """Get collision alert for a six-satellite pair. pair in ('ab', 'cd', 'ef')."""
    factories = {
        "ab": make_six_satellite_alert_ab,
        "cd": make_six_satellite_alert_cd,
        "ef": make_six_satellite_alert_ef,
    }
    factory = factories.get(pair.lower())
    if factory is None:
        raise ValueError(f"Unknown six_satellite pair '{pair}'. Use ab, cd, or ef.")
    return factory()


ALL_SCENARIOS = {
    "head_on": make_head_on_collision,
    "debris": make_debris_avoidance,
    "low_probability": make_low_probability,
    "three_way": make_three_way_conjunction,
}


def get_mock_alert(scenario: str = "head_on") -> CollisionAlert:
    """Get a mock collision alert for the given scenario."""
    factory = ALL_SCENARIOS.get(scenario)
    if factory is None:
        raise ValueError(
            f"Unknown scenario '{scenario}'. Choose from: {list(ALL_SCENARIOS)}"
        )
    return factory()


def write_mock_alerts_json(output_path: str | Path, scenario: str = "head_on") -> None:
    """Write a mock collision alert to a JSON file (simulates physics agent output)."""
    alert = get_mock_alert(scenario)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(alert.model_dump_json(indent=2))
