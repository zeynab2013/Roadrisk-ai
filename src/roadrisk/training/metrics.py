"""Validation metrics for the positive severity class.

The positive class is 1 (fatal or serious). Scores are probabilities of
that class. The default cutoff is 0.5. Phase 5 does not tune it. A later
caller may pass a threshold that was chosen without the 2025 test year.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

# If two models are this close on average precision, the lower Brier score wins.
AVERAGE_PRECISION_TIE = 0.005
DECISION_THRESHOLD = 0.5


def positive_class_metrics(
    y_true,
    y_score,
    *,
    threshold: float = DECISION_THRESHOLD,
) -> dict[str, object]:
    """Score one label vector. Undefined ranking metrics stay null.

    Precision, recall, F1, accuracy, and the confusion matrix use
    ``threshold``. Average precision, ROC-AUC, Brier score, and log loss
    use the probabilities and do not.
    """

    cutoff = _validate_threshold(threshold)
    labels = np.asarray(y_true).astype(int)
    scores = np.asarray(y_score, dtype=float)
    if labels.shape[0] != scores.shape[0]:
        raise ValueError("Labels and scores have different lengths")
    predicted = (scores >= cutoff).astype(int)
    matrix = confusion_matrix(labels, predicted, labels=[0, 1])
    both_classes = len(np.unique(labels)) == 2
    finite_scores = bool(scores.size) and bool(np.isfinite(scores).all())
    probabilities = finite_scores and bool(np.all((scores >= 0.0) & (scores <= 1.0)))
    average_precision, average_precision_status = _ranking(
        average_precision_score, labels, scores, both_classes
    )
    roc_auc, roc_auc_status = _ranking(roc_auc_score, labels, scores, both_classes)
    if probabilities:
        brier = float(brier_score_loss(labels, scores))
        brier_status = "defined"
        loss = float(log_loss(labels, scores, labels=[0, 1]))
        loss_status = "defined"
    else:
        brier = None
        brier_status = "undefined"
        loss = None
        loss_status = "undefined"
    if cutoff == DECISION_THRESHOLD:
        note = "Estimator default of 0.5. It was not tuned on validation or test."
    else:
        note = "Caller-supplied threshold. Ranking metrics do not use it."
    rows = int(labels.shape[0])
    correct = int((predicted == labels).sum()) if rows else 0
    return {
        "positive_label": 1,
        "threshold": cutoff,
        "threshold_note": note,
        "rows": rows,
        "positive_rows": int((labels == 1).sum()),
        "predicted_positive": int(predicted.sum()),
        "precision": float(precision_score(labels, predicted, pos_label=1, zero_division=0)),
        "recall": float(recall_score(labels, predicted, pos_label=1, zero_division=0)),
        "f1": float(f1_score(labels, predicted, pos_label=1, zero_division=0)),
        "accuracy": (correct / rows) if rows else None,
        "average_precision": average_precision,
        "average_precision_status": average_precision_status,
        "roc_auc": roc_auc,
        "roc_auc_status": roc_auc_status,
        "brier": brier,
        "brier_status": brier_status,
        "log_loss": loss,
        "log_loss_status": loss_status,
        "confusion_matrix": {
            "labels": [0, 1],
            "matrix": matrix.astype(int).tolist(),
            "order": "rows are true 0 then 1; columns are predicted 0 then 1",
        },
    }


def assert_metric_consistency(metrics: Mapping[str, object]) -> None:
    """Raise when the confusion matrix does not match the reported counts."""

    matrix = _metrics_matrix(metrics)
    true_negative, false_positive = matrix[0]
    false_negative, true_positive = matrix[1]
    total = true_negative + false_positive + false_negative + true_positive
    if total != metrics["rows"]:
        raise ValueError("Confusion-matrix counts do not match the row count")
    if false_positive + true_positive != metrics["predicted_positive"]:
        raise ValueError("Predicted-positive count does not match the confusion matrix")
    if false_negative + true_positive != metrics["positive_rows"]:
        raise ValueError("Positive-class count does not match the confusion matrix")


def _validate_threshold(threshold: float) -> float:
    value = float(threshold)
    if not np.isfinite(value) or value <= 0.0 or value > 1.0:
        raise ValueError("threshold must be finite and in the interval (0, 1]")
    return value


def _metrics_matrix(metrics: Mapping[str, object]) -> list[list[int]]:
    confusion = metrics["confusion_matrix"]
    if not isinstance(confusion, Mapping):
        raise ValueError("Metrics are missing a confusion matrix")
    matrix = confusion["matrix"]
    if not isinstance(matrix, list) or len(matrix) != 2:
        raise ValueError("Confusion matrix must have two rows")
    return [[int(value) for value in row] for row in matrix]


def choose_provisional(results: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Pick a provisional model from 2024 validation metrics.

    Average precision on the positive class is the ranking metric because
    the classes are uneven. A model must beat the dummy classifier on that
    metric to be eligible. When the leading scores are within
    ``AVERAGE_PRECISION_TIE``, the lower Brier score is preferred. If none
    beat the dummy, the dummy remains the provisional choice.
    """

    dummy = next((row for row in results if row["model"] == "dummy"), None)
    if dummy is None:
        raise ValueError("Model comparison is missing the dummy classifier")
    dummy_metrics = _metrics(dummy)
    dummy_ap = dummy_metrics["average_precision"]
    if not isinstance(dummy_ap, float):
        raise ValueError("Dummy average precision is undefined, so models cannot be compared")
    beating = []
    for row in results:
        score = _metrics(row)["average_precision"]
        if row["model"] != "dummy" and isinstance(score, float) and score > dummy_ap:
            beating.append(row)
    pool = beating or [dummy]
    best_ap = max(float(_metrics(row)["average_precision"]) for row in pool)
    close = [
        row
        for row in pool
        if best_ap - float(_metrics(row)["average_precision"]) <= AVERAGE_PRECISION_TIE
    ]
    chosen = min(close, key=_brier_then_name)
    return {
        "model": chosen["model"],
        "average_precision_tie": AVERAGE_PRECISION_TIE,
        "dummy_average_precision": dummy_ap,
        "models_beating_dummy_average_precision": [str(row["model"]) for row in beating],
        "rule": (
            "Rank defined positive-class average precision on the 2024 validation set. "
            "Keep models that beat the dummy classifier. If the best scores are within "
            f"{AVERAGE_PRECISION_TIE} average precision, choose the lower Brier score. "
            "If none beat the dummy, keep the dummy. The 0.5 threshold is not tuned, "
            "and 2025 is not used."
        ),
    }


def _ranking(function, labels, scores, both_classes: bool) -> tuple[float | None, str]:
    if not both_classes:
        return None, "undefined"
    try:
        return float(function(labels, scores)), "defined"
    except ValueError:
        return None, "undefined"


def _metrics(row: Mapping[str, object]) -> Mapping[str, object]:
    metrics = row["metrics"]
    if not isinstance(metrics, Mapping):
        raise ValueError("Each result needs a metrics object")
    return metrics


def _brier_then_name(row: Mapping[str, object]) -> tuple[float, str]:
    brier = _metrics(row)["brier"]
    penalty = float(brier) if isinstance(brier, float) else 1.0
    return penalty, str(row["model"])
