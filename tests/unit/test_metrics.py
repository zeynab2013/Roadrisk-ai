"""Metric invariants on synthetic arrays. These are not held-out evaluation results."""

from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from roadrisk.training.metrics import assert_metric_consistency, positive_class_metrics


def test_synthetic_metrics_use_aligned_fatal_or_serious_labels() -> None:
    metrics = positive_class_metrics([0, 1, 1, 0], [0.1, 0.2, 0.9, 0.8], threshold=0.5)
    assert metrics["positive_label"] == 1
    assert metrics["rows"] == 4
    assert metrics["confusion_matrix"]["labels"] == [0, 1]
    assert_metric_consistency(metrics)
    assert "2025" not in metrics["threshold_note"]
    assert "held-out" not in str(metrics)
    outside = positive_class_metrics([0, 1], [-0.1, 1.4])
    assert outside["brier"] is None
    assert outside["brier_status"] == "undefined"
    assert outside["log_loss_status"] == "undefined"


def test_misaligned_or_inconsistent_metrics_are_rejected() -> None:
    with pytest.raises(ValueError, match="different lengths"):
        positive_class_metrics([0, 1], [0.2])
    with pytest.raises(ValueError, match="threshold"):
        positive_class_metrics([0, 1], [0.2, 0.8], threshold=0.0)
    metrics = positive_class_metrics([0, 1], [0.2, 0.8])
    broken = dict(metrics)
    broken["rows"] = 99
    with pytest.raises(ValueError, match="row count"):
        assert_metric_consistency(broken)
    missing = {
        "rows": 0,
        "predicted_positive": 0,
        "positive_rows": 0,
        "confusion_matrix": "absent",
    }
    with pytest.raises(ValueError, match="confusion matrix"):
        assert_metric_consistency(missing)
