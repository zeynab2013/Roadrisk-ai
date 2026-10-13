"""Probability calibration fit on the training period only.

Sigmoid and isotonic calibrators use out-of-fold predictions from
``CalibratedClassifierCV``. They are not fit on the 2024 validation rows
or on the 2025 test rows. The uncalibrated reference is the already fitted
Phase 5 model, which is not modified.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold

from roadrisk.data.errors import FeatureContractError
from roadrisk.training.columns import LABEL_COLUMN
from roadrisk.training.metrics import assert_metric_consistency, positive_class_metrics
from roadrisk.training.pipelines import SEED
from roadrisk.training.population import assert_excludes_test, assert_validation_frame
from roadrisk.training.scoring import feature_matrix, positive_scores

# A calibrator must improve both probability scores. A drop in average
# precision larger than this is rejected even when Brier and log loss fall.
AVERAGE_PRECISION_DROP_LIMIT = 0.01
# Within this Brier gap, prefer the parametric sigmoid calibrator.
BRIER_PREFERENCE_BAND = 0.001
CALIBRATION_METHODS = ("sigmoid", "isotonic")
RELIABILITY_BINS = 10

CALIBRATION_RULE = (
    "Compare the Phase 5 uncalibrated model with sigmoid and isotonic "
    "calibrators on 2024. Keep a calibrator only when its Brier score and "
    "log loss are both lower and positive-class average precision falls by "
    f"at most {AVERAGE_PRECISION_DROP_LIMIT}. If both qualify, choose the "
    f"lower Brier score. If those Brier scores are within {BRIER_PREFERENCE_BAND}, "
    "keep sigmoid. Otherwise keep the uncalibrated model. "
    "2024 is used to choose the method, so those scores are selection results. "
    "2025 is not used."
)


def fit_calibrator(estimator, train, *, method: str, cv_splits: int):
    """Fit one calibrator on training rows. The estimator is cloned by sklearn."""

    if method not in CALIBRATION_METHODS:
        raise ValueError(f"Unknown calibration method: {method}")
    if cv_splits < 2:
        raise ValueError("Calibration cross-validation needs at least two splits")
    assert_excludes_test(train, purpose="calibration")
    years = set(train["collision_year"].astype(str))
    if not years or not years <= {"2021", "2022", "2023"}:
        raise FeatureContractError("Calibration data must be the 2021-2023 training period")
    if set(train["split"].astype(str)) != {"training"}:
        raise FeatureContractError("Calibration data must use the training split")
    labels = train[LABEL_COLUMN].to_numpy()
    folder = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=SEED)
    calibrated = CalibratedClassifierCV(
        estimator=estimator,
        method=method,
        cv=folder,
        ensemble=False,
        n_jobs=1,
    )
    calibrated.fit(feature_matrix(train), labels)
    return calibrated


def reliability_table(y_true, y_score, *, n_bins: int = RELIABILITY_BINS) -> dict[str, object]:
    """Equal-width reliability bins and an expected calibration error."""

    labels = np.asarray(y_true).astype(int)
    scores = np.asarray(y_score, dtype=float)
    if labels.shape[0] != scores.shape[0]:
        raise ValueError("Labels and scores have different lengths")
    if n_bins < 2:
        raise ValueError("Reliability summary needs at least two bins")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows: list[dict[str, object]] = []
    total = int(labels.shape[0])
    error = 0.0
    finite = bool(total) and bool(np.isfinite(scores).all())
    for index in range(n_bins):
        low = float(edges[index])
        high = float(edges[index + 1])
        if index == n_bins - 1:
            mask = (scores >= low) & (scores <= high)
        else:
            mask = (scores >= low) & (scores < high)
        count = int(mask.sum())
        if count and finite:
            mean_predicted = float(scores[mask].mean())
            observed = float(labels[mask].mean())
            error += (count / total) * abs(observed - mean_predicted)
        else:
            mean_predicted = None
            observed = None
        rows.append(
            {
                "bin_low": low,
                "bin_high": high,
                "count": count,
                "mean_predicted": mean_predicted,
                "observed_positive_rate": observed,
            }
        )
    return {
        "n_bins": n_bins,
        "expected_calibration_error": float(error) if finite and total else None,
        "bins": rows,
    }


def summarize_candidate(method: str, y_true, y_score) -> dict[str, object]:
    """Validation metrics plus a reliability table for one probability source."""

    metrics = positive_class_metrics(y_true, y_score)
    assert_metric_consistency(metrics)
    return {
        "method": method,
        "metrics": metrics,
        "reliability": reliability_table(y_true, y_score),
    }


def choose_calibration(candidates: list[Mapping[str, object]]) -> dict[str, object]:
    """Apply the written calibration rule. Does not look at a test year."""

    by_method = {str(row["method"]): row for row in candidates}
    missing = [name for name in ("none", *CALIBRATION_METHODS) if name not in by_method]
    if missing:
        raise ValueError("Calibration comparison is missing: " + ", ".join(missing))
    base = _metrics(by_method["none"])
    base_brier = _required_float(base, "brier")
    base_loss = _required_float(base, "log_loss")
    base_ap = _required_float(base, "average_precision")
    eligible: list[Mapping[str, object]] = []
    for method in CALIBRATION_METHODS:
        metrics = _metrics(by_method[method])
        better_probability = (
            _required_float(metrics, "brier") < base_brier
            and _required_float(metrics, "log_loss") < base_loss
        )
        ranking_held = base_ap - _required_float(metrics, "average_precision") <= (
            AVERAGE_PRECISION_DROP_LIMIT + 1e-12
        )
        if better_probability and ranking_held:
            eligible.append(by_method[method])
    if not eligible:
        chosen = "none"
        reason = (
            "Neither calibrator lowered both Brier score and log loss on 2024 "
            "without dropping average precision by more than "
            f"{AVERAGE_PRECISION_DROP_LIMIT}. The uncalibrated model is retained."
        )
    else:
        best_brier = min(_required_float(_metrics(row), "brier") for row in eligible)
        close = [
            row
            for row in eligible
            if _required_float(_metrics(row), "brier") - best_brier <= BRIER_PREFERENCE_BAND
        ]
        sigmoid = [row for row in close if row["method"] == "sigmoid"]
        picked = sigmoid[0] if sigmoid else min(close, key=_brier_then_method)
        chosen = str(picked["method"])
        reason = (
            f"{chosen} lowered 2024 Brier score and log loss and kept average precision "
            f"within {AVERAGE_PRECISION_DROP_LIMIT} of the uncalibrated model."
        )
    return {
        "method": chosen,
        "average_precision_drop_limit": AVERAGE_PRECISION_DROP_LIMIT,
        "brier_preference_band": BRIER_PREFERENCE_BAND,
        "rule": CALIBRATION_RULE,
        "reason": reason,
    }


def score_fitted_candidates(reference, calibrated: Mapping[str, object], validation) -> list[dict]:
    """Score the frozen reference and each fitted calibrator on validation rows."""

    assert_validation_frame(validation, purpose="calibration comparison")
    labels = validation[LABEL_COLUMN].to_numpy()
    rows = [
        summarize_candidate("none", labels, positive_scores(reference, validation)),
    ]
    for method, estimator in calibrated.items():
        rows.append(summarize_candidate(method, labels, positive_scores(estimator, validation)))
    return rows


def _metrics(row: Mapping[str, object]) -> Mapping[str, object]:
    metrics = row["metrics"]
    if not isinstance(metrics, Mapping):
        raise ValueError("Each calibration candidate needs metrics")
    return metrics


def _required_float(metrics: Mapping[str, object], key: str) -> float:
    value = metrics[key]
    if not isinstance(value, (int, float)):
        raise ValueError(f"Calibration metric {key} is undefined")
    return float(value)


def _brier_then_method(row: Mapping[str, object]) -> tuple[float, str]:
    return _required_float(_metrics(row), "brier"), str(row["method"])
