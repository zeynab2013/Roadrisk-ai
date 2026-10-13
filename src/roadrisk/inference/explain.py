"""Local explanations for one reported collision's severity score.

Each feature is replaced, one at a time, with the missing value the frozen
pipeline already imputes. The change in predicted probability is a local
sensitivity. It is not a cause, and it is not a global importance rank.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from roadrisk.data.errors import DataError, FeatureContractError
from roadrisk.features.spec import APPROVED, APPROVED_NAMES
from roadrisk.inference.risk import assign_category
from roadrisk.training.run import normalize_model_frame
from roadrisk.training.scoring import positive_scores

FIELD_MEANING = {field.name: field.meaning for field in APPROVED}
EXPLANATION_LIMITATION = (
    "The probability is the model's estimate that this reported "
    "personal-injury collision was fatal or serious rather than slight. "
    "It is not the probability that a collision occurs, and it is not a "
    "judgement that a road is safe or unsafe. Replacing one recorded field "
    "with missing shows how this fitted model responds. It does not show "
    "that the field caused the collision or the injury. A global importance "
    "ranking is a different summary and is not a reason for this row."
)
NOT_ESTIMATED = "Whether a collision occurs."
CLASS_LABELS = {0: "slight", 1: "fatal_or_serious"}


def explain_frame(
    estimator,
    frame: pd.DataFrame,
    *,
    binary_threshold: float,
    bands: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Explain each row. Feature order follows the approved specification.

    ``binary_threshold`` must be the frozen Phase 6 threshold. This function
    does not default to 0.5, and it will not score a 2025 or test-split row.
    """

    threshold = _threshold(binary_threshold)
    if len(frame) == 0:
        raise DataError("Explanation needs at least one row")
    _refuse_held_out(frame)
    prepared = normalize_model_frame(frame)
    _require_columns(prepared)
    base = _probabilities(positive_scores(estimator, prepared))
    changes = []
    for name in APPROVED_NAMES:
        perturbed = prepared.copy()
        perturbed[name] = np.nan
        alternate = _probabilities(positive_scores(estimator, perturbed))
        changes.append((name, alternate))
    explanations = []
    for index in range(len(prepared)):
        probability = float(base[index])
        predicted = int(probability >= threshold)
        sensitivities = []
        for name, alternate in changes:
            without = float(alternate[index])
            sensitivities.append(
                {
                    "feature": name,
                    "field_records": FIELD_MEANING[name],
                    "observed_value": _observed(frame.iloc[index][name]),
                    "reference": "pipeline missing value",
                    "probability_if_missing": without,
                    "probability_change": probability - without,
                }
            )
        row = {
            "probability": probability,
            "binary_threshold": threshold,
            "predicted_class": predicted,
            "predicted_class_label": CLASS_LABELS[predicted],
            "observed_inputs": {
                name: _observed(frame.iloc[index][name]) for name in APPROVED_NAMES
            },
            "local_sensitivity": sensitivities,
            "limitation": EXPLANATION_LIMITATION,
            "not_estimated": NOT_ESTIMATED,
            "category": None,
        }
        if bands is not None:
            row["category"] = assign_category(probability, bands)
        explanations.append(row)
    return explanations


def global_permutation_summary(
    estimator,
    frame: pd.DataFrame,
    *,
    sample_size: int = 2000,
    n_repeats: int = 3,
    seed: int = 42,
) -> dict[str, object]:
    """Global average-precision drop on a 2024 validation sample.

    This is not an explanation of one prediction. The frame must already be
    the 2024 validation split.
    """

    from sklearn.inspection import permutation_importance

    from roadrisk.training.columns import LABEL_COLUMN
    from roadrisk.training.population import assert_validation_frame
    from roadrisk.training.scoring import feature_matrix

    assert_validation_frame(frame, purpose="global permutation importance")
    if LABEL_COLUMN not in frame.columns:
        raise FeatureContractError("Global importance needs the validation label")
    sample = _stratified_sample(frame, sample_size, seed)
    result = permutation_importance(
        estimator,
        feature_matrix(sample),
        sample[LABEL_COLUMN].to_numpy(),
        scoring="average_precision",
        n_repeats=n_repeats,
        random_state=seed,
        n_jobs=1,
    )
    rows = []
    for name, mean, std in zip(
        APPROVED_NAMES, result.importances_mean, result.importances_std, strict=True
    ):
        rows.append(
            {
                "feature": name,
                "mean_average_precision_drop": float(mean),
                "std_average_precision_drop": float(std),
            }
        )
    rows.sort(key=lambda item: (-item["mean_average_precision_drop"], item["feature"]))
    return {
        "scope": "global",
        "period": "2024",
        "sample_rows": int(len(sample)),
        "n_repeats": n_repeats,
        "seed": seed,
        "scoring": "average_precision",
        "not_a_local_explanation": True,
        "features": rows,
    }


def _stratified_sample(frame: pd.DataFrame, sample_size: int, seed: int) -> pd.DataFrame:
    from roadrisk.training.columns import LABEL_COLUMN

    if len(frame) <= sample_size:
        return frame
    rng = np.random.default_rng(seed)
    pieces = []
    labels = frame[LABEL_COLUMN].to_numpy()
    for label in (0, 1):
        positions = np.flatnonzero(labels == label)
        if positions.size == 0:
            continue
        take = int(round(sample_size * positions.size / len(frame)))
        take = min(max(take, 1), positions.size)
        chosen = rng.choice(positions, size=take, replace=False)
        pieces.append(frame.iloc[np.sort(chosen)])
    sample = pd.concat(pieces, ignore_index=True)
    if len(sample) > sample_size:
        return sample.iloc[:sample_size].copy()
    return sample


def _refuse_held_out(frame: pd.DataFrame) -> None:
    if "collision_year" in frame.columns and (frame["collision_year"].astype(str) == "2025").any():
        raise FeatureContractError("This explanation path will not score 2025 rows")
    if "split" in frame.columns and (frame["split"].astype(str) == "test").any():
        raise FeatureContractError("This explanation path will not score the test split")


def _require_columns(frame: pd.DataFrame) -> None:
    missing = [name for name in APPROVED_NAMES if name not in frame.columns]
    if missing:
        raise FeatureContractError("Explanation is missing columns: " + ", ".join(missing))


def _probabilities(scores) -> np.ndarray:
    values = np.asarray(scores, dtype=float)
    if values.size == 0 or not np.isfinite(values).all():
        raise DataError("The model returned a missing probability")
    if np.any((values < 0.0) | (values > 1.0)):
        raise DataError("The model returned a probability outside [0, 1]")
    return values


def _threshold(threshold: float) -> float:
    value = float(threshold)
    if not np.isfinite(value) or value <= 0.0 or value > 1.0:
        raise DataError("The classification threshold must be finite and in (0, 1]")
    return value


def _observed(value: object) -> object:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        return value
    return value if not isinstance(value, np.generic) else value.item()
