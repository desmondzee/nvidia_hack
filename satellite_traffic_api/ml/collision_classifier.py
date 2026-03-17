"""XGBoost collision risk classifier.

Trained at import time on synthetically generated data derived from domain
knowledge. Acts as a supplement to the rule-based _compute_risk() — the final
risk level is the maximum (most severe) of both classifiers, so rules always
serve as a safety floor.

Feature interactions captured beyond hard-threshold rules:
  - Debris + high closing speed + miss < 2 km → elevated risk
  - Imminent TCA (< 1 day) + any close conjunction → elevated risk
  - DEBRIS type with moderate miss distance → elevated risk
"""
from __future__ import annotations

import numpy as np
import xgboost as xgb

from satellite_traffic_api.models.conjunction import ConjunctionEvent
from satellite_traffic_api.models.space_weather import SpaceWeatherSummary
from satellite_traffic_api.models.context import RiskLevel

_OBJECT_TYPE_RISK: dict[str, int] = {
    "PAYLOAD": 0,
    "UNKNOWN": 1,
    "ROCKET_BODY": 2,
    "DEBRIS": 3,
}

_LABEL_TO_RISK: dict[int, RiskLevel] = {
    0: "NOMINAL",
    1: "ELEVATED",
    2: "HIGH",
    3: "CRITICAL",
}

_RISK_TO_LABEL: dict[str, int] = {v: k for k, v in _LABEL_TO_RISK.items()}


def _extract_features(c: ConjunctionEvent, sw: SpaceWeatherSummary) -> list[float]:
    prob = c.collision_probability or 0.0
    has_prob = float(c.collision_probability is not None)
    speed = c.relative_speed_km_s if c.relative_speed_km_s is not None else 7.5
    obj_risk = float(_OBJECT_TYPE_RISK.get(c.secondary_object_type, 1))
    return [
        c.miss_distance_km,
        prob,
        has_prob,
        speed,
        c.days_until_tca,
        obj_risk,
        sw.current_kp,
        sw.atmospheric_drag_enhancement_factor,
    ]


def _rule_label(miss_km: float, prob: float, kp: float) -> int:
    """Mirrors existing _compute_risk thresholds — used to label synthetic data."""
    if miss_km < 0.2 or prob > 1e-3:
        return 3  # CRITICAL
    if miss_km < 1.0 or prob > 1e-4:
        return 2  # HIGH
    if miss_km < 5.0 or kp >= 7:
        return 1  # ELEVATED
    return 0  # NOMINAL


def _generate_training_data() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    n = 400

    # Features drawn from realistic orbital distributions
    miss = np.exp(rng.uniform(np.log(0.05), np.log(50.0), n))   # 0.05–50 km, log scale
    has_prob = rng.random(n) > 0.3                                # 70% have a probability
    prob = np.where(
        has_prob,
        np.exp(rng.uniform(np.log(1e-7), np.log(1e-2), n)),
        0.0,
    )
    speed = rng.uniform(1.0, 15.0, n)
    days = rng.uniform(0.05, 7.0, n)
    obj_type = rng.integers(0, 4, n).astype(float)  # 0=PAYLOAD … 3=DEBRIS
    kp = rng.uniform(0.0, 9.0, n)
    drag = 1.0 + np.clip(kp - 5.0, 0.0, None) * 0.1

    X = np.column_stack([miss, prob, has_prob.astype(float), speed, days, obj_type, kp, drag])

    # Base labels from rule logic
    y = np.array([_rule_label(m, p, k) for m, p, k in zip(miss, prob, kp)])

    # Interaction bumps: features that together indicate higher risk than rules alone
    fast_and_close = (speed > 10.0) & (miss < 2.0)
    imminent = (days < 1.0) & (miss < 5.0)
    debris_close = (obj_type == 3) & (miss < 3.0)

    for mask in (fast_and_close, imminent, debris_close):
        y = np.where(mask, np.minimum(y + 1, 3), y)

    return X, y.astype(int)


_TRAIN_PARAMS = {
    "objective": "multi:softmax",
    "num_class": 4,
    "max_depth": 4,
    "eta": 0.2,            # learning_rate in native API
    "eval_metric": "mlogloss",
    "verbosity": 0,
    "seed": 42,
}
_NUM_BOOST_ROUND = 50


class CollisionClassifier:
    """XGBoost multi-class risk classifier, trained once at instantiation.

    Uses the native xgboost.train() API (no scikit-learn dependency).
    """

    def __init__(self) -> None:
        X, y = _generate_training_data()
        dtrain = xgb.DMatrix(X, label=y)
        self._model = xgb.train(_TRAIN_PARAMS, dtrain, num_boost_round=_NUM_BOOST_ROUND)

    def predict_risk(
        self,
        conjunctions: list[ConjunctionEvent],
        space_weather: SpaceWeatherSummary,
    ) -> RiskLevel:
        """Return the worst predicted risk level across all conjunctions."""
        if not conjunctions:
            return "NOMINAL"
        X = np.array([_extract_features(c, space_weather) for c in conjunctions])
        dtest = xgb.DMatrix(X)
        preds = self._model.predict(dtest)  # float array of class indices
        worst = int(preds.max())
        return _LABEL_TO_RISK[worst]
