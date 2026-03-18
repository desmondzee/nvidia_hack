"""Load and parse collision alerts from JSON (file or dict)."""

import json
from pathlib import Path

from src.models.physics import CollisionAlert


def load_alert_from_json(data: dict) -> CollisionAlert:
    """Parse a single collision alert from a JSON-compatible dict."""
    return CollisionAlert.model_validate(data)


def load_alerts_from_file(path: str | Path) -> list[CollisionAlert]:
    """Load collision alerts from a JSON file.

    The file may contain a single alert (object) or multiple alerts (array).
    """
    with open(path) as f:
        raw = json.load(f)

    if isinstance(raw, list):
        return [CollisionAlert.model_validate(item) for item in raw]
    return [CollisionAlert.model_validate(raw)]
