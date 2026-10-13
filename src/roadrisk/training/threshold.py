"""Choose one classification threshold on validation scores only."""

from __future__ import annotations

from roadrisk.training.columns import LABEL_COLUMN
from roadrisk.training.metrics import (
    DECISION_THRESHOLD,
    assert_metric_consistency,
    positive_class_metrics,
)
from roadrisk.training.population import assert_validation_frame

# Keep 0.5 unless validation F1 improves by at least this amount.
F1_IMPROVEMENT_MARGIN = 0.01
THRESHOLD_GRID = tuple(round(step / 100, 2) for step in range(5, 100, 5))

THRESHOLD_OBJECTIVE = (
    "Research operating point for fatal or serious severity, given a reported "
    "personal-injury collision. On 2024 validation scores, maximize positive-class "
    "F1. Keep the 0.5 reference unless F1 improves by at least "
    f"{F1_IMPROVEMENT_MARGIN}. This is not a safety, clinical, or operational "
    "optimum, and it is not a measured cost ratio. False positives and false "
    "negatives are both reported. 2025 is not used."
)


def threshold_grid(y_true, y_score) -> list[dict[str, object]]:
    """Score every grid point, including the 0.5 reference."""

    if DECISION_THRESHOLD not in THRESHOLD_GRID:
        raise ValueError("The 0.5 reference is missing from the threshold grid")
    rows = []
    for cutoff in THRESHOLD_GRID:
        metrics = positive_class_metrics(y_true, y_score, threshold=cutoff)
        assert_metric_consistency(metrics)
        rows.append({"threshold": cutoff, "metrics": metrics})
    return rows


def choose_threshold(y_true, y_score) -> dict[str, object]:
    """Apply the F1 rule. The returned grid is the evidence, not a test score."""

    rows = threshold_grid(y_true, y_score)
    reference = next(row for row in rows if row["threshold"] == DECISION_THRESHOLD)
    reference_f1 = float(reference["metrics"]["f1"])
    best_f1 = max(float(row["metrics"]["f1"]) for row in rows)
    if best_f1 < reference_f1 + F1_IMPROVEMENT_MARGIN:
        chosen = reference
        reason = (
            "No threshold on the grid improved 2024 positive-class F1 by at least "
            f"{F1_IMPROVEMENT_MARGIN} over 0.5. The reference threshold is retained."
        )
    else:
        best = [row for row in rows if float(row["metrics"]["f1"]) == best_f1]
        chosen = min(
            best,
            key=lambda row: (abs(float(row["threshold"]) - 0.5), -float(row["threshold"])),
        )
        reason = (
            f"Threshold {chosen['threshold']} improved 2024 positive-class F1 by at least "
            f"{F1_IMPROVEMENT_MARGIN} over 0.5. Ties keep the threshold closer to 0.5, "
            "then the higher threshold."
        )
    return {
        "threshold": chosen["threshold"],
        "reference_threshold": DECISION_THRESHOLD,
        "f1_improvement_margin": F1_IMPROVEMENT_MARGIN,
        "objective": THRESHOLD_OBJECTIVE,
        "reason": reason,
        "selected_metrics": chosen["metrics"],
        "grid": rows,
    }


def choose_threshold_on_validation(validation, scores) -> dict[str, object]:
    """Select a threshold from validation rows. Test rows are rejected."""

    assert_validation_frame(validation, purpose="threshold selection")
    return choose_threshold(validation[LABEL_COLUMN].to_numpy(), scores)
