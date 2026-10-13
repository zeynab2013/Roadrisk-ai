"""Map calibrated severity probabilities to research bands.

LOW, MEDIUM, and HIGH describe the model's estimated probability that a
reported personal-injury collision was fatal or serious. They are not the
probability that a collision occurs, and they are not road-safety grades.

The Phase 6 classification threshold stays separate. A probability at or
above that threshold is the positive class even when the band is LOW or
MEDIUM.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from roadrisk.data.errors import DataError, FeatureContractError
from roadrisk.training.population import assert_validation_frame
from roadrisk.training.scoring import positive_scores

LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
CATEGORIES = (LOW, MEDIUM, HIGH)
LOWER_QUANTILE = 0.50
UPPER_QUANTILE = 0.90

BAND_METHOD = (
    "On scores from the frozen calibrated model for the 2024 validation "
    "split only, the lower boundary is the 0.50 quantile and the upper "
    "boundary is the 0.90 quantile. LOW is strictly below the lower "
    "boundary. MEDIUM includes the lower boundary and stops before the "
    "upper boundary. HIGH includes the upper boundary. The quantiles "
    "describe the distribution of model output. They are not the Phase 6 "
    "classification threshold and they are not a safety standard. "
    "2025 scores and labels are not used."
)


def choose_category_boundaries(scores) -> dict[str, object]:
    """Return the two band boundaries for one validation score vector."""

    values = np.asarray(scores, dtype=float)
    if values.size == 0:
        raise DataError("Category boundaries need at least one validation score")
    if not np.isfinite(values).all() or np.any((values < 0.0) | (values > 1.0)):
        raise DataError("Category boundaries need finite probabilities in [0, 1]")
    lower = float(np.quantile(values, LOWER_QUANTILE, method="linear"))
    upper = float(np.quantile(values, UPPER_QUANTILE, method="linear"))
    validate_boundaries(lower, upper)
    return {
        "low_below": lower,
        "high_at_or_above": upper,
        "lower_quantile": LOWER_QUANTILE,
        "upper_quantile": UPPER_QUANTILE,
        "method": BAND_METHOD,
        "rows": int(values.size),
    }


def boundaries_from_validation(estimator, frame) -> dict[str, object]:
    """Score a 2024 validation frame and derive band boundaries.

    The frame is rejected before scoring when it is not exactly the 2024
    validation split.
    """

    assert_validation_frame(frame, purpose="category boundaries")
    scores = positive_scores(estimator, frame)
    chosen = choose_category_boundaries(scores)
    chosen["score_mean"] = float(np.mean(scores))
    return chosen


def validate_boundaries(lower: float, upper: float) -> None:
    """Raise unless the two cuts are finite, ordered, and inside (0, 1)."""

    if not np.isfinite(lower) or not np.isfinite(upper):
        raise DataError("Category boundaries must be finite")
    if not 0.0 < float(lower) < float(upper) < 1.0:
        raise DataError(
            "Category boundaries must satisfy 0 < lower < upper < 1. "
            f"Received lower={lower} and upper={upper}."
        )


def assign_category(probability: float, boundaries: Mapping[str, object]) -> str:
    """Assign one band. The lower cut is MEDIUM. The upper cut is HIGH."""

    value = float(probability)
    if not np.isfinite(value) or value < 0.0 or value > 1.0:
        raise DataError("A category needs a finite probability in [0, 1]")
    lower = float(boundaries["low_below"])
    upper = float(boundaries["high_at_or_above"])
    validate_boundaries(lower, upper)
    if value < lower:
        return LOW
    if value < upper:
        return MEDIUM
    return HIGH


def load_risk_bands(
    path,
    *,
    expected_decision_sha256: str | None = None,
    expected_artifact_sha256: str | None = None,
) -> dict[str, object]:
    """Read a band file. An incompatible or unordered file raises."""

    if not path.is_file():
        raise DataError(f"Risk-band configuration is missing: {path}")
    try:
        payload = json_loads(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise DataError(f"Risk-band configuration is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise DataError("Risk-band configuration must be a JSON object")
    for key in ("low_below", "high_at_or_above", "method", "binary_threshold"):
        if key not in payload:
            raise DataError(f"Risk-band configuration is missing {key}")
    validate_boundaries(float(payload["low_below"]), float(payload["high_at_or_above"]))
    if payload.get("test_period_used") is not False:
        raise FeatureContractError("Risk bands must record that 2025 was not used")
    if (
        expected_decision_sha256 is not None
        and payload.get("decision_sha256") != expected_decision_sha256
    ):
        raise DataError("Risk bands are not tied to this frozen decision")
    if (
        expected_artifact_sha256 is not None
        and payload.get("selected_artifact_sha256") != expected_artifact_sha256
    ):
        raise DataError("Risk bands are not tied to this frozen pipeline")
    return payload


def json_loads(path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))
