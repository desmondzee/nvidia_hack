"""JSON schema contract for the physics agent.

Share the output of `get_collision_alert_schema()` with the physics agent
developer so they produce JSON matching the expected format.
"""

import json

from src.models.physics import CollisionAlert


def get_collision_alert_schema() -> dict:
    """Return the JSON Schema for CollisionAlert."""
    return CollisionAlert.model_json_schema()


def print_schema() -> None:
    """Print the schema as formatted JSON (convenience for sharing)."""
    print(json.dumps(get_collision_alert_schema(), indent=2))


if __name__ == "__main__":
    print_schema()
